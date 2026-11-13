"""HTTP surface. Server-side authorisation: owners act only on their own shop;
operators run planning/sandbox/dispatch but can never approve on an owner's behalf."""
import json
import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, File, Form, UploadFile

from .. import capture as capture_mod
from ..capture_media import extract_invoice, transcribe_audio, capabilities, CaptureMediaError
from ..request_models import NeedRequest, InventoryRequest, CaptureRequest, QuoteRequest, PlanningRequest, ShopPreferences
from .. import db, lifecycle, sandbox, seed as seed_mod
from ..config import CASE_ID, DEFAULT_RADIUS_KM, DEFAULT_TIME_LIMIT_MS, OPERATOR_PIN, OWNER_PIN
from ..planner import build_context, enumerate_cycles, plan as run_plan

router = APIRouter(prefix="/api")
_executor = ThreadPoolExecutor(max_workers=2)


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def current_actor(authorization: str = Header(default=""), conn=None) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    row = conn.execute("SELECT * FROM sessions WHERE token=?", (authorization[7:],)).fetchone()
    if not row:
        raise HTTPException(401, "invalid or expired session")
    return {"token": row["token"], "role": row["role"], "shop_id": row["shop_id"]}


def auth(conn=Depends(get_conn), authorization: str = Header(default="")) -> dict:
    return current_actor(authorization, conn)


def require_owner_of(actor: dict, shop_id: int):
    if actor["role"] != "owner" or actor["shop_id"] != shop_id:
        raise HTTPException(403, "owner token for this shop required")


def require_operator(actor):
    if actor["role"] != "operator":
        raise HTTPException(403, "operator role required")


def require_shop_access(actor, shop_id):
    if actor["role"] == "owner":
        require_owner_of(actor, shop_id)


def require_plan_access(actor, row):
    if actor["role"] == "owner" and actor["shop_id"] not in db.jload(row["participants"], []):
        raise HTTPException(403, "this plan does not include your shop")


def scoped_idempotency(actor, operation, key):
    if len(key) > 200:
        raise HTTPException(422, "idempotency key is too long")
    return f"{actor['role']}:{actor['shop_id']}:{operation}:{key}" if key else None


def cached_write(conn, key, body):
    if not key:
        return None
    row = conn.execute("SELECT response FROM idempotency WHERE key=?", (key,)).fetchone()
    if not row:
        return None
    stored = db.jload(row["response"], {})
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    if stored.get("_fingerprint") != fingerprint:
        raise HTTPException(409, "idempotency key was already used with different input")
    return stored["response"]


def remember_write(conn, key, body, response):
    if key:
        fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        conn.execute("INSERT INTO idempotency(key,response,created_at) VALUES (?,?,?)",
                     (key, json.dumps({"_fingerprint": fingerprint, "response": response}), db.now_iso()))


# ---------- session ----------

@router.post("/session")
def create_session(body: dict, conn=Depends(get_conn)):
    role = body.get("role")
    pin = str(body.get("pin", ""))
    shop_id = body.get("shop_id")
    if role == "operator":
        if pin != OPERATOR_PIN:
            raise HTTPException(401, "wrong operator PIN")
    elif role == "owner":
        if not shop_id:
            raise HTTPException(400, "owner session needs shop_id")
        if pin != OWNER_PIN:
            raise HTTPException(401, "wrong owner PIN")
    else:
        raise HTTPException(400, "role must be owner or operator")
    if role == "owner" and not conn.execute("SELECT id FROM shops WHERE id=?", (shop_id,)).fetchone():
        raise HTTPException(404, "shop not found")
    token = uuid.uuid4().hex
    with db.tx(conn):
        conn.execute("INSERT INTO sessions(token, role, shop_id, created_at) VALUES (?,?,?,?)",
                     (token, role, shop_id, db.now_iso()))
    shop = conn.execute("SELECT name FROM shops WHERE id=?", (shop_id,)).fetchone() if shop_id else None
    return {"token": token, "role": role, "shop_id": shop_id,
            "shop_name": shop["name"] if shop else None}


# ---------- reference data ----------

@router.get("/health")
def health(conn=Depends(get_conn)):
    return {"ok": True, "shops": conn.execute("SELECT COUNT(*) c FROM shops").fetchone()["c"],
            "products": conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"],
            "capture_capabilities": capabilities(),
            "open_reservations": conn.execute(
                "SELECT COUNT(*) c FROM reservations WHERE status='active'").fetchone()["c"]}


@router.get("/shops")
def shops(conn=Depends(get_conn), authorization: str = Header(default="")):
    """Unauthenticated callers (login shop-picker) get names/coords only; no cash limits."""
    try:
        actor = current_actor(authorization, conn)
        authed = True
    except HTTPException:
        authed = False
        actor = None
    rows = []
    for r in conn.execute("SELECT * FROM shops ORDER BY id"):
        d = dict(r)
        if not authed or (actor["role"] == "owner" and actor["shop_id"] != d["id"]):
            d.pop("cash_limit_paise", None)
        rows.append(d)
    return rows


@router.get("/products")
def products(conn=Depends(get_conn), actor=Depends(auth)):
    rows = [dict(r) for r in conn.execute("SELECT * FROM products ORDER BY brand, name")]
    aliases = {}
    for r in conn.execute("SELECT product_id, alias_text FROM aliases"):
        aliases.setdefault(r["product_id"], []).append(r["alias_text"])
    for row in rows:
        row["aliases"] = aliases.get(row["id"], [])
    return rows


@router.get("/shops/{shop_id}/stock")
def shop_stock(shop_id: int, conn=Depends(get_conn), actor=Depends(auth)):
    require_shop_access(actor, shop_id)
    rows = []
    q = """SELECT l.*, p.name product_name, p.name_hi product_name_hi, p.emoji, p.unit, p.pack_size
           FROM stock_lots l JOIN products p ON p.id=l.product_id WHERE l.shop_id=? ORDER BY p.name"""
    reserved = {r["lot_id"]: r["s"] for r in conn.execute(
        "SELECT lot_id, SUM(qty) s FROM reservations WHERE status='active' AND expires_at > ? GROUP BY lot_id",
        (db.now_iso(),))}
    for r in conn.execute(q, (shop_id,)):
        d = dict(r)
        d["lot_id"] = d["id"]
        d["reserved_qty"] = reserved.get(d["id"], 0)
        d["available_qty"] = max(0, d["qty"] - d["retained_floor"] - d["reserved_qty"])
        d["permit_share"] = bool(d["permit_share"])
        d["slow"] = bool(d["slow"])
        d["days_to_expiry"] = (date.fromisoformat(d["expiry_date"]) - date.today()).days \
            if d["expiry_date"] else None
        rows.append(d)
    return rows


@router.get("/shops/{shop_id}/needs")
def shop_needs(shop_id: int, conn=Depends(get_conn), actor=Depends(auth)):
    require_shop_access(actor, shop_id)
    rows = []
    q = """SELECT n.*, p.name product_name, p.name_hi product_name_hi, p.emoji
           FROM needs n JOIN products p ON p.id=n.product_id
           WHERE n.shop_id=? AND n.status='open' ORDER BY n.urgency DESC, n.id"""
    for r in conn.execute(q, (shop_id,)):
        d = dict(r)
        d["alt_product_ids"] = db.jload(d["alt_product_ids"], [])
        rows.append(d)
    return rows


@router.get("/supplier-quotes")
def supplier_quotes(product_id: int | None = None, conn=Depends(get_conn), actor=Depends(auth)):
    if product_id:
        rows = conn.execute("SELECT * FROM supplier_quotes WHERE product_id=?", (product_id,))
    else:
        rows = conn.execute("SELECT * FROM supplier_quotes")
    return [dict(r) for r in rows]


# ---------- owner-confirmed writes ----------

@router.post("/needs")
def add_need(body: NeedRequest, conn=Depends(get_conn), actor=Depends(auth)):
    body = body.model_dump()
    shop_id = body["shop_id"]
    if actor["role"] == "owner":
        require_owner_of(actor, shop_id)
    if not conn.execute("SELECT id FROM shops WHERE id=?", (shop_id,)).fetchone():
        raise HTTPException(404, "shop not found")
    for pid in [body["product_id"], *body.get("alt_product_ids", [])]:
        if not conn.execute("SELECT id FROM products WHERE id=?", (pid,)).fetchone():
            raise HTTPException(404, "product not found")
    with db.tx(conn):
        cur = conn.execute(
            "INSERT INTO needs(shop_id, product_id, qty, urgency, alt_product_ids, budget_paise,"
            " min_shelf_days, status, created_at) VALUES (?,?,?,?,?,?,?, 'open', ?)",
            (shop_id, body["product_id"], body["qty"], body.get("urgency", "normal"),
             json.dumps(body.get("alt_product_ids", [])), body.get("budget_paise"),
             body.get("min_shelf_days", 14), db.now_iso()))
        db.log_event(conn, actor["role"], "need.added", "need", cur.lastrowid, {"shop_id": shop_id})
    return {"id": cur.lastrowid}


@router.delete("/needs/{need_id}")
def remove_need(need_id: int, conn=Depends(get_conn), actor=Depends(auth)):
    with db.tx(conn):
        need = conn.execute("SELECT * FROM needs WHERE id=?", (need_id,)).fetchone()
        if not need:
            raise HTTPException(404, "need not found")
        if actor["role"] == "owner":
            require_owner_of(actor, need["shop_id"])
        conn.execute("UPDATE needs SET status='deleted' WHERE id=?", (need_id,))
        db.log_event(conn, actor["role"], "need.deleted", "need", need_id, {})
    return {"ok": True}


@router.post("/supplier-quotes")
def add_quote(body: QuoteRequest, conn=Depends(get_conn), actor=Depends(auth)):
    require_operator(actor)
    body = body.model_dump()
    if not conn.execute("SELECT id FROM products WHERE id=?", (body["product_id"],)).fetchone():
        raise HTTPException(404, "product not found")
    with db.tx(conn):
        cur = conn.execute(
            "INSERT INTO supplier_quotes(product_id, supplier_name, price_paise, min_order_packs, lead_days)"
            " VALUES (?,?,?,?,?)",
            (body["product_id"], body.get("supplier_name", "Gupta Distributors"),
             body["price_paise"], body.get("min_order_packs", 1), body.get("lead_days", 1)))
    return {"id": cur.lastrowid}


@router.post("/inventory/confirm")
def inventory_confirm(body: InventoryRequest, conn=Depends(get_conn), actor=Depends(auth),
                      idempotency_key: str = Header(default="")):
    body = body.model_dump(exclude_none=True)
    shop_id = body["shop_id"]
    require_shop_access(actor, shop_id)
    key = scoped_idempotency(actor, f"inventory:{shop_id}", idempotency_key)
    with db.tx(conn):
        cached = cached_write(conn, key, body)
        if cached is not None:
            return cached
        if not conn.execute("SELECT id FROM shops WHERE id=?", (shop_id,)).fetchone():
            raise HTTPException(404, "shop not found")
        applied = []
        for ch in body["changes"]:
            pid = ch["product_id"]
            if not conn.execute("SELECT id FROM products WHERE id=?", (pid,)).fetchone():
                raise HTTPException(404, "product not found")
            if ch.get("lot_id"):
                lot = conn.execute("SELECT * FROM stock_lots WHERE id=? AND shop_id=?",
                                   (ch["lot_id"], shop_id)).fetchone()
                if not lot or lot["product_id"] != pid:
                    raise HTTPException(404, "lot/product does not belong to this shop")
                if ch["expected_version"] != lot["version"]:
                    raise HTTPException(409, "stock changed; refresh before confirming")
                new_qty = ch.get("qty", lot["qty"] + ch.get("delta", 0))
                floor = ch.get("retained_floor", lot["retained_floor"])
                if new_qty < 0 or floor > new_qty:
                    raise HTTPException(422, "quantity must be non-negative and cover the retained floor")
                if ch.get("permit_share", lot["permit_share"]) and (
                        ch.get("cost_paise", lot["cost_paise"]) <= 0 or
                        not ch.get("expiry_date", lot["expiry_date"])):
                    raise HTTPException(422, "confirm purchase cost and label date before sharing this lot")
                delta = new_qty - lot["qty"]
                conn.execute(
                    "UPDATE stock_lots SET qty=?,cost_paise=COALESCE(?,cost_paise),"
                    " expiry_date=COALESCE(?,expiry_date),condition=COALESCE(?,condition),"
                    " permit_share=COALESCE(?,permit_share),slow=COALESCE(?,slow),"
                    " retained_floor=?,version=version+1,updated_at=? WHERE id=?",
                    (new_qty, ch.get("cost_paise"), ch.get("expiry_date"), ch.get("condition"),
                     ch.get("permit_share"), ch.get("slow"), floor, db.now_iso(), ch["lot_id"]))
                lot_id = ch["lot_id"]
            else:
                qty, floor = ch["qty"], ch.get("retained_floor", 0)
                if floor > qty:
                    raise HTTPException(422, "retained floor exceeds quantity")
                if ch.get("permit_share") and (ch.get("cost_paise", 0) <= 0 or not ch.get("expiry_date")):
                    raise HTTPException(422, "confirm purchase cost and label date before sharing this lot")
                cur = conn.execute(
                    "INSERT INTO stock_lots(shop_id,product_id,qty,cost_paise,expiry_date,condition,"
                    "permit_share,slow,retained_floor,version,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,1,?,?)",
                    (shop_id,pid,qty,ch.get("cost_paise",0),ch.get("expiry_date"),ch.get("condition","sealed"),
                     int(ch.get("permit_share",False)),int(ch.get("slow",False)),floor,db.now_iso(),db.now_iso()))
                lot_id, delta = cur.lastrowid, qty
            conn.execute(
                "INSERT INTO inventory_log(shop_id,lot_id,product_id,delta,reason,actor,source,ts)"
                " VALUES (?,?,?,?,?,?,'confirm',?)",
                (shop_id,lot_id,pid,delta,body["reason"],actor["role"],db.now_iso()))
            applied.append({"lot_id":lot_id,"product_id":pid,"delta":delta})
        conn.execute("UPDATE shops SET version=version+1 WHERE id=?", (shop_id,))
        version = conn.execute("SELECT version FROM shops WHERE id=?", (shop_id,)).fetchone()["version"]
        db.log_event(conn,actor["role"],"inventory.confirmed","shop",shop_id,{"changes":applied})
        response = {"applied":applied,"shop_version":version}
        remember_write(conn,key,body,response)
    return response


@router.patch("/shops/{shop_id}/preferences")
def shop_preferences(shop_id: int, body: ShopPreferences, conn=Depends(get_conn), actor=Depends(auth)):
    require_owner_of(actor, shop_id)
    with db.tx(conn):
        shop = conn.execute("SELECT * FROM shops WHERE id=?", (shop_id,)).fetchone()
        if not shop:
            raise HTTPException(404, "shop not found")
        held = conn.execute("SELECT COALESCE(SUM(amount_paise),0) amount FROM cash_reservations WHERE shop_id=? AND status IN ('active','pending_operator')", (shop_id,)).fetchone()["amount"]
        if body.cash_limit_paise < held:
            raise HTTPException(409, "cash limit cannot be lower than existing plan holds")
        if shop["version"] != body.expected_version:
            raise HTTPException(409, "shop changed; refresh before saving preferences")
        conn.execute("UPDATE shops SET cash_limit_paise=?,sharing_opt_in=?,version=version+1 WHERE id=?",
                     (body.cash_limit_paise,int(body.sharing_opt_in),shop_id))
        db.log_event(conn,f"owner:{shop_id}","shop.preferences","shop",shop_id,
                     {"cash_limit_paise":body.cash_limit_paise,"sharing_opt_in":body.sharing_opt_in})
    return {"shop_id":shop_id,"version":shop["version"]+1,"cash_limit_paise":body.cash_limit_paise,
            "sharing_opt_in":body.sharing_opt_in}


@router.get("/shops/{shop_id}/preferences")
def read_shop_preferences(shop_id: int, conn=Depends(get_conn), actor=Depends(auth)):
    require_shop_access(actor, shop_id)
    lifecycle.sweep_expired(conn)
    shop = conn.execute("SELECT * FROM shops WHERE id=?", (shop_id,)).fetchone()
    if not shop:
        raise HTTPException(404, "shop not found")
    held = conn.execute("SELECT COALESCE(SUM(amount_paise),0) amount FROM cash_reservations "
                        "WHERE shop_id=? AND status IN ('active','pending_operator')", (shop_id,)).fetchone()["amount"]
    return {"shop_id":shop_id,"version":shop["version"],"cash_limit_paise":shop["cash_limit_paise"],
            "sharing_opt_in":bool(shop["sharing_opt_in"]),"held_cash_paise":held}


# ---------- capture ----------

@router.post("/captures")
def create_capture(body: CaptureRequest, conn=Depends(get_conn), actor=Depends(auth)):
    body = body.model_dump()
    shop_id = body["shop_id"]
    if actor["role"] == "owner":
        require_owner_of(actor, shop_id)
    result = capture_mod.parse_capture(conn, body.get("text", ""))
    with db.tx(conn):
        cur = conn.execute(
            "INSERT INTO captures(shop_id, modality, raw_text, extracted, status, created_at)"
            " VALUES (?, 'text', ?, ?, ?, ?)",
            (shop_id, body.get("text", ""), json.dumps(result), result["status"], db.now_iso()))
        db.log_event(conn, actor["role"], "capture.created", "capture", cur.lastrowid,
                     {"status": result["status"], "engine": result["engine"]})
    return {"capture_id": cur.lastrowid, **result}


def _media_capture(conn, actor, shop_id, file_data, filename, content_type, modality):
    require_shop_access(actor, shop_id)
    if not conn.execute("SELECT id FROM shops WHERE id=?", (shop_id,)).fetchone():
        raise HTTPException(404, "shop not found")
    try:
        extracted = (transcribe_audio if modality == "audio" else extract_invoice)(file_data, filename, content_type)
    except CaptureMediaError as exc:
        if exc.code != "unavailable":
            raise HTTPException(413 if exc.code == "too_large" else 422, str(exc))
        return {"capture_id":None,"status":"failed","proposals":[],"questions":[str(exc)],
                "engine":modality,"fallback":"manual-form","warnings":[str(exc)]}
    result = capture_mod.parse_capture(conn, extracted["text"])
    result["warnings"] = extracted.get("warnings", [])
    result["source_engine"] = extracted["engine"]
    with db.tx(conn):
        cur = conn.execute(
            "INSERT INTO captures(shop_id,modality,raw_text,extracted,status,created_at) VALUES (?,?,?,?,?,?)",
            (shop_id,modality,extracted["text"],json.dumps(result),result["status"],db.now_iso()))
        db.log_event(conn,actor["role"],"capture.created","capture",cur.lastrowid,
                     {"status":result["status"],"engine":extracted["engine"]})
    return {"capture_id":cur.lastrowid,**result}


@router.post("/captures/audio")
def capture_audio(shop_id: int = Form(...), file: UploadFile = File(...),
                  conn=Depends(get_conn), actor=Depends(auth)):
    require_shop_access(actor, shop_id)
    data = file.file.read(8 * 1024 * 1024 + 1)
    return _media_capture(conn,actor,shop_id,data,file.filename or "",file.content_type or "","audio")


@router.post("/captures/invoice")
def capture_invoice(shop_id: int = Form(...), file: UploadFile = File(...),
                    conn=Depends(get_conn), actor=Depends(auth)):
    require_shop_access(actor, shop_id)
    data = file.file.read(8 * 1024 * 1024 + 1)
    return _media_capture(conn,actor,shop_id,data,file.filename or "",file.content_type or "","invoice")


@router.post("/captures/{capture_id}/confirm")
def confirm_capture(capture_id: int, body: dict, conn=Depends(get_conn), actor=Depends(auth),
                    idempotency_key: str = Header(default="")):
    cap = conn.execute("SELECT * FROM captures WHERE id=?", (capture_id,)).fetchone()
    if not cap:
        raise HTTPException(404, "capture not found")
    if actor["role"] == "owner":
        require_owner_of(actor, cap["shop_id"])
    key = scoped_idempotency(actor, f"capture:{capture_id}", idempotency_key)
    cached = cached_write(conn, key, body)
    if cached is not None:
        return cached
    try:
        resp = capture_mod.confirm_capture(conn, capture_id, body.get("edits", []), actor["role"],
                                           idempotency_key=key, request_body=body)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return resp


# ---------- planning ----------

def _execute_run(run_id: int, case_id: str, params: dict):
    conn = db.connect()
    try:
        with db.tx(conn):
            conn.execute("UPDATE planning_runs SET status='running' WHERE id=?", (run_id,))
        t0 = __import__("time").perf_counter()
        # Keep solver inputs and their provenance in the same short snapshot.
        # Never stamp old solver output with versions read *after* solving.
        with db.tx(conn):
            ctx = build_context(conn, params)
            source_shops = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM shops")}
            source_lots = [dict(r) for r in conn.execute("SELECT * FROM stock_lots")]
            source_needs = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM needs")}
            source_quotes = [dict(r) for r in conn.execute("SELECT * FROM supplier_quotes")]
        cycles = enumerate_cycles(ctx)
        proposal = run_plan(ctx, cycles, params)
        participants = set(proposal.get("participants", []))
        exchanged = {(leg["from_shop"], leg["product_id"]) for c in proposal.get("cycles", []) for leg in c["legs"]}
        need_ids = {c["need_id"] for c in proposal.get("coverage", []) if c.get("qty_covered", 0) > 0}
        quote_ids = {q["id"] for q in source_quotes for p in proposal.get("purchases", [])
                     if q["product_id"] == p["product_id"] and q["price_paise"] == p["unit_price_paise"]
                     and q["min_order_packs"] <= p["qty"]}
        proposal["input_versions"] = {
            "shops": {str(s): source_shops[s]["version"] for s in participants},
            "lots": {str(r["id"]): r["version"] for r in source_lots if (r["shop_id"],r["product_id"]) in exchanged},
            "needs": {str(n): source_needs[n] for n in need_ids},
            "quotes": {str(q["id"]): q for q in source_quotes if q["id"] in quote_ids},
        }
        elapsed = int((__import__("time").perf_counter() - t0) * 1000)
        with db.tx(conn):
            plan_id = None
            if proposal["cycles"] or proposal["purchases"]:
                plan_id = lifecycle.create_plan(conn, case_id, run_id, proposal)
                db.log_event(conn, "agent", "plan.proposed", "plan", plan_id,
                             {"solver": proposal["solver"]})
            conn.execute(
                "UPDATE planning_runs SET status='done', result=?, finished_at=? WHERE id=?",
                (json.dumps({"plan_id": plan_id, "proposal": proposal, "elapsed_ms": elapsed}),
                 db.now_iso(), run_id))
    except Exception as e:   # noqa: BLE001 — surface the error to the run poller
        with db.tx(conn):
            conn.execute("UPDATE planning_runs SET status='error', error=?, finished_at=? WHERE id=?",
                         (str(e), db.now_iso(), run_id))
    finally:
        conn.close()


@router.post("/planning-runs")
def start_run(body: PlanningRequest, conn=Depends(get_conn), actor=Depends(auth)):
    body = body.model_dump()
    if actor["role"] != "operator":
        raise HTTPException(403, "operator role required")
    case_id = body.get("case_id", CASE_ID)
    params = body.get("params") or {}
    params.setdefault("time_limit_ms", DEFAULT_TIME_LIMIT_MS)
    params.setdefault("min_shelf_days", 14)
    params.setdefault("radius_km", DEFAULT_RADIUS_KM)
    params.setdefault("include_purchases", True)
    with db.tx(conn):
        cur = conn.execute(
            "INSERT INTO planning_runs(case_id, status, params, created_at) VALUES (?, 'queued', ?, ?)",
            (case_id, json.dumps(params), db.now_iso()))
        run_id = cur.lastrowid
        db.log_event(conn, "operator", "planning.started", "run", run_id, {"params": params})
    _executor.submit(_execute_run, run_id, case_id, params)
    return {"run_id": run_id}


@router.get("/planning-runs/{run_id}")
def get_run(run_id: int, conn=Depends(get_conn), actor=Depends(auth)):
    require_operator(actor)
    lifecycle.sweep_expired(conn)
    run = conn.execute("SELECT * FROM planning_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "run not found")
    out = {"run_id": run_id, "status": run["status"], "progress":
           {"queued": 5, "running": 55, "done": 100, "error": 100}[run["status"]],
           "error": run["error"]}
    if run["result"]:
        res = db.jload(run["result"], {})
        prop = res.get("proposal", {})
        out.update({"plan_id": res.get("plan_id"), "elapsed_ms": res.get("elapsed_ms"),
                    "solver": prop.get("solver"), "why_not": prop.get("why_not"),
                    "log": prop.get("log", [])})
    else:
        out.update({"solver": None, "why_not": None, "log": []})
    return out


@router.get("/shops/{shop_id}/plans")
def shop_plans(shop_id: int, limit: int = 20, conn=Depends(get_conn), actor=Depends(auth)):
    require_shop_access(actor, shop_id)
    limit = min(100, max(1, limit))
    lifecycle.sweep_expired(conn)
    rows = []
    for p in conn.execute("SELECT * FROM plans ORDER BY id DESC LIMIT 200"):
        participants = db.jload(p["participants"], [])
        if shop_id not in participants:
            continue
        if len(rows) >= limit:
            break
        prop = db.jload(p["proposal"], {})
        rows.append({
            "id": p["id"], "version": p["version"], "status": p["status"],
            "created_at": p["created_at"], "inputs_hash": p["inputs_hash"],
            "participants": participants,
            "cycles": prop.get("cycles", []), "purchases": prop.get("purchases", []),
            "coverage": prop.get("coverage", []), "costs": prop.get("costs", {}),
            "assumptions": prop.get("assumptions", []), "solver": prop.get("solver"),
            "why_not": prop.get("why_not"),
            "approval_history": _approval_history(conn, p),
        })
    return rows


def _approval_history(conn, plan):
    # A plan row is immutable; material changes create a new plan/version.
    return [{**dict(row), "at": row["decided_at"], "inputs_hash": plan["inputs_hash"]}
            for row in conn.execute("SELECT * FROM approvals WHERE plan_id=? ORDER BY id", (plan["id"],))]


# ---------- cluster analytics ----------

def _plan_totals(prop: dict) -> dict:
    cov = prop.get("coverage") or []
    needed = sum(r["qty_needed"] for r in cov)
    covered = sum(min(r["qty_covered"], r["qty_needed"]) for r in cov)
    cash = prop.get("costs", {}).get("cash_out_by_shop", {})
    return {
        "cycles": len(prop.get("cycles", [])),
        "purchases": len(prop.get("purchases", [])),
        "coverage_pct": round(100 * covered / needed, 1) if needed else 0.0,
        "cash_out_paise": sum(v for v in cash.values()),
        "slow_packs": sum(c.get("slow_packs_redeployed", 0) for c in prop.get("cycles", [])),
    }


@router.get("/cases/{case_id}/summary")
def case_summary(case_id: str, conn=Depends(get_conn), actor=Depends(auth)):
    require_operator(actor)
    """Cluster KPIs for the operator dashboard."""
    from datetime import date as _date, datetime as _dt

    today = _date.today()
    stock_packs = stock_value = 0
    near14 = near30 = slow_value = slow_packs = 0
    cats = {}
    for r in conn.execute(
            "SELECT l.qty, l.cost_paise, l.expiry_date, l.slow, p.category FROM stock_lots l"
            " JOIN products p ON p.id = l.product_id"):
        v = r["qty"] * r["cost_paise"]
        stock_packs += r["qty"]
        stock_value += v
        cats[r["category"]] = cats.get(r["category"], 0) + v
        if r["expiry_date"]:
            d = (_date.fromisoformat(r["expiry_date"]) - today).days
            if 0 <= d <= 14:
                near14 += v
            if 0 <= d <= 30:
                near30 += v
        if r["slow"]:
            slow_packs += r["qty"]
            slow_value += v
    needs = [dict(r) for r in conn.execute("SELECT qty, urgency FROM needs WHERE status='open'")]
    last_plan = conn.execute("SELECT * FROM plans WHERE case_id=? ORDER BY id DESC LIMIT 1", (case_id,)).fetchone()
    plan_info = None
    if last_plan:
        prop = db.jload(last_plan["proposal"], {})
        plan_info = {"id": last_plan["id"], "version": last_plan["version"],
                     "status": last_plan["status"], "solver_status": (prop.get("solver") or {}).get("status"),
                     **_plan_totals(prop)}
    return {
        "shops": conn.execute("SELECT COUNT(*) c FROM shops WHERE withdrawn=0").fetchone()["c"],
        "sharing_on": conn.execute("SELECT COUNT(*) c FROM shops WHERE sharing_opt_in=1 AND withdrawn=0").fetchone()["c"],
        "stock_packs": stock_packs, "stock_value_paise": stock_value,
        "near_expiry_14_value_paise": near14, "near_expiry_30_value_paise": near30,
        "slow_packs": slow_packs, "slow_value_paise": slow_value,
        "open_needs": len(needs), "open_need_packs": sum(n["qty"] for n in needs),
        "urgent_packs": sum(n["qty"] for n in needs if n["urgency"] == "urgent"),
        "active_reservations": conn.execute(
            "SELECT COUNT(*) c FROM reservations WHERE status='active' AND expires_at > ?",
            (db.now_iso(),)).fetchone()["c"],
        "last_plan": plan_info,
        "top_categories": sorted(
            [{"category": k, "value_paise": v} for k, v in cats.items()],
            key=lambda x: -x["value_paise"])[:6],
    }


@router.get("/cases/{case_id}/directory")
def case_directory(case_id: str, conn=Depends(get_conn), actor=Depends(auth)):
    require_operator(actor)
    """One batched query for the operator directory: per-shop lot/need/value counts.
    Replaces N×2 per-shop fetches in the dashboard."""
    shops = {}
    for r in conn.execute("SELECT id, name, name_hi, owner_name, lat, lng, cash_limit_paise,"
                          " sharing_opt_in, withdrawn, disconnected FROM shops ORDER BY id"):
        d = dict(r)
        d.update({"lots": 0, "packs": 0, "stock_value_paise": 0, "near_expiry_lots": 0,
                  "slow_packs": 0, "open_needs": 0, "need_packs": 0})
        shops[d["id"]] = d
    for r in conn.execute(
            """SELECT shop_id, COUNT(*) lots, COALESCE(SUM(qty),0) packs,
               COALESCE(SUM(qty*cost_paise),0) value_paise,
               SUM(CASE WHEN expiry_date IS NOT NULL AND expiry_date >= date('now')
                    AND expiry_date <= date('now','+30 day') THEN 1 ELSE 0 END) near_expiry_lots,
               COALESCE(SUM(CASE WHEN slow=1 THEN qty ELSE 0 END),0) slow_packs
               FROM stock_lots GROUP BY shop_id"""):
        if r["shop_id"] in shops:
            shops[r["shop_id"]].update({"lots": r["lots"], "packs": r["packs"],
                                        "stock_value_paise": r["value_paise"],
                                        "near_expiry_lots": r["near_expiry_lots"] or 0,
                                        "slow_packs": r["slow_packs"]})
    for r in conn.execute(
            "SELECT shop_id, COUNT(*) open_needs, COALESCE(SUM(qty),0) need_packs"
            " FROM needs WHERE status='open' GROUP BY shop_id"):
        if r["shop_id"] in shops:
            shops[r["shop_id"]].update({"open_needs": r["open_needs"], "need_packs": r["need_packs"]})
    return list(shops.values())


@router.get("/shops/{shop_id}/pulse")
def shop_pulse(shop_id: int, conn=Depends(get_conn), actor=Depends(auth)):
    require_shop_access(actor, shop_id)
    """Owner-facing 'my shelf today' aggregates for one shop."""
    from datetime import date as _date

    today = _date.today()
    packs = value = near_value = slow_packs = 0
    lots = 0
    for r in conn.execute("SELECT qty, cost_paise, expiry_date, slow FROM stock_lots WHERE shop_id=?",
                          (shop_id,)):
        v = r["qty"] * r["cost_paise"]
        lots += 1
        packs += r["qty"]
        value += v
        if r["slow"]:
            slow_packs += r["qty"]
        if r["expiry_date"]:
            d = (_date.fromisoformat(r["expiry_date"]) - today).days
            if 0 <= d <= 30:
                near_value += v
    needs = conn.execute("SELECT COALESCE(SUM(qty),0) p, COUNT(*) c FROM needs"
                         " WHERE shop_id=? AND status='open'", (shop_id,)).fetchone()
    reserved = conn.execute(
        "SELECT COALESCE(SUM(r.qty),0) q FROM reservations r"
        " JOIN stock_lots l ON l.id = r.lot_id WHERE l.shop_id=? AND r.status='active'"
        " AND r.expires_at > ?", (shop_id, db.now_iso())).fetchone()["q"]
    return {"lots": lots, "packs": packs, "stock_value_paise": value,
            "near_expiry_value_paise": near_value, "slow_packs": slow_packs,
            "open_needs": needs["c"], "need_packs": needs["p"], "reserved_packs": reserved}


@router.get("/shops/{shop_id}/expiry-actions")
def expiry_actions(shop_id: int, within_days: int = 60, conn=Depends(get_conn), actor=Depends(auth)):
    require_shop_access(actor, shop_id)
    """Advisory only: near-expiry lots and what could absorb them. Never a safety claim."""
    from datetime import date as _date

    today = _date.today()
    need_rows = conn.execute(
        "SELECT n.shop_id, n.product_id, n.qty FROM needs n"
        " JOIN shops s ON s.id = n.shop_id WHERE n.status='open' AND s.withdrawn=0").fetchall()
    quotes = {r["product_id"] for r in conn.execute("SELECT DISTINCT product_id FROM supplier_quotes")}
    out = []
    for r in conn.execute(
            "SELECT l.*, p.name product_name, p.name_hi product_name_hi, p.emoji FROM stock_lots l"
            " JOIN products p ON p.id = l.product_id WHERE l.shop_id=? AND l.expiry_date IS NOT NULL"
            " AND l.qty > 0", (shop_id,)):
        days = (_date.fromisoformat(r["expiry_date"]) - today).days
        if days > within_days:
            continue
        matched = sum(n["qty"] for n in need_rows
                      if n["product_id"] == r["product_id"] and n["shop_id"] != shop_id)
        if matched:
            suggestion, note = "exchange", "Other shops in the cluster need this product"
        elif r["product_id"] in quotes:
            suggestion, note = "return_to_distributor", "A supplier quote exists; a return may be negotiable"
        else:
            suggestion, note = "use_first", "No exchange or return match found — consider placing it where it sells first"
        out.append({"lot_id": r["id"], "product_id": r["product_id"], "product_name": r["product_name"],
                    "product_name_hi": r["product_name_hi"], "emoji": r["emoji"], "qty": r["qty"],
                    "expiry_date": r["expiry_date"], "days_left": days,
                    "value_paise": r["qty"] * r["cost_paise"],
                    "matched_need_packs": matched, "suggestion": suggestion, "note": note})
    out.sort(key=lambda x: x["days_left"])
    return out


@router.get("/cases/{case_id}/plans")
def case_plan_history(case_id: str, limit: int = 30, conn=Depends(get_conn), actor=Depends(auth)):
    require_operator(actor)
    """Version history of plans for the case, newest first."""
    lifecycle.sweep_expired(conn)
    rows = []
    for p in conn.execute("SELECT * FROM plans WHERE case_id=? ORDER BY id DESC LIMIT ?", (case_id, limit)):
        prop = db.jload(p["proposal"], {})
        rows.append({"id": p["id"], "version": p["version"], "status": p["status"],
                     "created_at": p["created_at"], "supersedes_id": p["supersedes_id"],
                     "inputs_hash": p["inputs_hash"],
                     "solver_status": (prop.get("solver") or {}).get("status"),
                     **_plan_totals(prop)})
    return rows


@router.get("/plans/{plan_id}")
def get_plan(plan_id: int, conn=Depends(get_conn), actor=Depends(auth)):
    lifecycle.sweep_expired(conn)
    plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if not plan:
        raise HTTPException(404, "plan not found")
    require_plan_access(actor, plan)
    prop = db.jload(plan["proposal"], {})
    approvals = _approval_history(conn, plan)
    return {**prop, "id": plan_id, "case_id": plan["case_id"], "version": plan["version"],
            "status": plan["status"], "created_at": plan["created_at"],
            "approval_expires_at": plan["approval_expires_at"],
            "inputs_hash": plan["inputs_hash"], "participants": db.jload(plan["participants"], []),
            "supersedes_id": plan["supersedes_id"], "approval_history": approvals}


@router.get("/plans/{plan_id}/status")
def plan_status(plan_id: int, conn=Depends(get_conn), actor=Depends(auth)):
    lifecycle.sweep_expired(conn)
    plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if not plan:
        raise HTTPException(404, "plan not found")
    require_plan_access(actor, plan)
    participants = db.jload(plan["participants"], [])
    approvals = [dict(r) for r in conn.execute("SELECT * FROM approvals WHERE plan_id=?", (plan_id,))]
    approved_shops = [a["shop_id"] for a in approvals if a["decision"] == "approved"]
    reservations = [dict(r) for r in conn.execute(
        "SELECT r.*, l.shop_id, p.name product_name FROM reservations r"
        " JOIN stock_lots l ON l.id=r.lot_id JOIN products p ON p.id=l.product_id"
        " WHERE r.plan_id=? ORDER BY r.id", (plan_id,))]
    actions = [dict(r) for r in conn.execute(
        "SELECT * FROM sandbox_actions WHERE plan_id=? ORDER BY seq", (plan_id,))]
    return {"status": plan["status"], "version": plan["version"], "inputs_hash": plan["inputs_hash"],
            "approval_expires_at": plan["approval_expires_at"],
            "approvals": approvals, "approvals_missing": [s for s in participants if s not in approved_shops],
            "reservations": reservations, "sandbox_actions": actions}


@router.post("/plans/{plan_id}/submit")
def submit_plan(plan_id: int, conn=Depends(get_conn), actor=Depends(auth)):
    require_operator(actor)
    try:
        return lifecycle.submit_for_approval(conn, plan_id, actor["role"])
    except lifecycle.Conflict as e:
        raise HTTPException(e.status, str(e))


@router.post("/plans/{plan_id}/approve")
def approve_plan(plan_id: int, conn=Depends(get_conn), actor=Depends(auth)):
    if actor["role"] != "owner":
        raise HTTPException(403, "only the shop owner can approve; operators cannot approve on an owner's behalf")
    try:
        return lifecycle.approve(conn, plan_id, actor["shop_id"], f"owner:{actor['shop_id']}")
    except lifecycle.Conflict as e:
        raise HTTPException(e.status, str(e))


@router.post("/plans/{plan_id}/reject")
def reject_plan(plan_id: int, body: dict, conn=Depends(get_conn), actor=Depends(auth)):
    if actor["role"] != "owner":
        raise HTTPException(403, "only the shop owner can reject")
    try:
        return lifecycle.reject(conn, plan_id, actor["shop_id"], body.get("reason", ""), f"owner:{actor['shop_id']}")
    except lifecycle.Conflict as e:
        raise HTTPException(e.status, str(e))


@router.post("/plans/{plan_id}/cancel")
def cancel_plan(plan_id: int, conn=Depends(get_conn), actor=Depends(auth)):
    if actor["role"] != "operator":
        raise HTTPException(403, "operator role required")
    try:
        return lifecycle.cancel(conn, plan_id, "operator")
    except lifecycle.Conflict as e:
        raise HTTPException(e.status, str(e))


@router.post("/plans/{plan_id}/dispatch")
def dispatch_plan(plan_id: int, conn=Depends(get_conn), actor=Depends(auth)):
    if actor["role"] != "operator":
        raise HTTPException(403, "operator role required")
    try:
        return lifecycle.dispatch(conn, plan_id, "operator")
    except lifecycle.Conflict as e:
        raise HTTPException(e.status, str(e))


# ---------- sandbox ----------

@router.post("/sandbox/inject")
def sandbox_inject(body: dict, conn=Depends(get_conn), actor=Depends(auth)):
    if actor["role"] != "operator":
        raise HTTPException(403, "operator role required")
    try:
        with db.tx(conn):
            rec = sandbox.inject(conn, body, "operator")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return rec


@router.post("/sandbox/reset")
def sandbox_reset(conn=Depends(get_conn), actor=Depends(auth)):
    if actor["role"] != "operator":
        raise HTTPException(403, "operator role required")
    with db.tx(conn):
        sandbox.reset(conn, "operator")
    return {"ok": True}


@router.get("/sandbox/state")
def sandbox_state(conn=Depends(get_conn), actor=Depends(auth)):
    require_operator(actor)
    return sandbox.get_state(conn)


# ---------- events / evidence ----------

@router.get("/cases/{case_id}/events")
def case_events(case_id: str, limit: int = 200, conn=Depends(get_conn), actor=Depends(auth)):
    require_operator(actor)
    limit = min(1000, max(1, limit))
    rows = conn.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"id": r["id"], "ts": r["ts"], "actor": r["actor"], "event_type": r["event_type"],
             "ref_type": r["ref_type"], "ref_id": r["ref_id"],
             "payload": db.jload(r["payload"], {})} for r in rows]


@router.get("/cases/{case_id}/export")
def case_export(case_id: str, conn=Depends(get_conn), actor=Depends(auth)):
    require_operator(actor)
    plans = []
    for p in conn.execute("SELECT * FROM plans WHERE case_id=? ORDER BY id", (case_id,)):
        prop = db.jload(p["proposal"], {})
        plans.append({"plan_id": p["id"], "version": p["version"], "status": p["status"],
                      "solver": prop.get("solver"), "costs": prop.get("costs"),
                      "coverage": prop.get("coverage"), "created_at": p["created_at"],
                      "inputs_hash": p["inputs_hash"]})
    events = conn.execute("SELECT ts, actor, event_type, ref_type, ref_id FROM audit_events ORDER BY id").fetchall()
    # pseudonymous export: shop names replaced by ids only
    return {"case_id": case_id, "exported_at": db.now_iso(), "plans": plans,
            "event_count": len(events), "note": "Anonymised: shops appear as ids; no customer, khata or payment data is included.",
            "events": [dict(r) for r in events]}
