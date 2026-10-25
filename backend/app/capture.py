"""Capture interpretation. Rules-first and fully local; an Ollama hook may enrich
proposals when a model is running, but every quantity stays a proposal until the
owner confirms. Ambiguous phrases produce clarification questions, never records."""
import json
import re
import urllib.request

from . import db
from .config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT_S

QTY_WORDS = r"(?:pack(?:et)?s?|pcs?|pieces?|units?|kg|kilo(?:s)?|g|gram(?:s)?|ltr|litre|L|dozen|नग|पैकेट|पैकिट|किलो|ग्राम|लीटर|दर्जन)"
NEED_WORDS = re.compile(r"(chahiye|need|needs|required|kam hai|कम है|चाहिए|ज़रूरत|जरूरत)", re.I)
STOCK_WORDS = re.compile(r"(stock|aaya|aa gaya|mila|add|hai|आया|मिला|स्टॉक|जोड़|है)", re.I)
PRICE_REF = re.compile(r"(?:₹|rs\.?|रु)?\s*(\d+)\s*(?:wala|vala|वाला|रुपये|रुपए|rupees?|rs)", re.I)
PRICE_LEAD = re.compile(r"(?:₹|rs\.?)\s*(\d+)", re.I)


def _load_aliases(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT a.alias_text t, a.product_id p, a.lang, pr.name, pr.name_hi, pr.emoji,"
        " pr.brand, pr.category, pr.pack_size, pr.unit FROM aliases a"
        " JOIN products pr ON pr.id = a.product_id").fetchall()
    seen = {}
    for r in rows:
        seen.setdefault(r["t"].lower().strip(), []).append(dict(r))
    return sorted(
        [{"text": t, "matches": ms, "score": len(t)} for t, ms in seen.items()],
        key=lambda x: -x["score"])


def _find_qty(text: str, span: tuple[int, int]) -> tuple[int | None, str | None, int | None]:
    """Quantity+unit near an alias match, and a ₹ price reference if present."""
    lo, hi = max(0, span[0] - 40), min(len(text), span[1] + 40)
    window = text[lo:hi]
    price = None
    for rx in (PRICE_REF, PRICE_LEAD):
        m = rx.search(window)
        if m:
            price = int(m.group(1)) * 100
            break
    m = re.search(r"(\d+(?:\.\d+)?)\s*(" + QTY_WORDS + r")?", window, re.I)
    qty, unit = None, None
    if m:
        candidate = float(m.group(1))
        same_as_price = price is not None and int(candidate) * 100 == price
        if not (same_as_price and not m.group(2)):
            # "₹10 wala biscuit": 10 is the price, not a quantity
            qty = int(candidate) if candidate == int(candidate) else candidate
            unit = (m.group(2) or "").lower() or None
    return qty, unit, price


def parse_text(conn, text: str) -> dict:
    aliases = _load_aliases(conn)
    lower = text.lower()
    matched_spans = []
    proposals = []
    taken = []

    for a in aliases:
        for m in re.finditer(re.escape(a["text"]), lower):
            span = m.span()
            if any(s < span[1] and e > span[0] for s, e in taken):
                continue
            taken.append(span)
            matched_spans.append((a, span))

    if not matched_spans:
        return {"status": "failed",
                "proposals": [],
                "questions": ["Could not identify any product. Try the product name, e.g. 'Parle-G 20 packet'. / कोई उत्पाद नहीं पहचाना गया। उत्पाद का नाम लिखें, जैसे 'पारले-जी 20 पैकेट'।"],
                "engine": "rules"}

    kind_hint = "need" if NEED_WORDS.search(text) else "stock_update"
    questions = []
    for a, span in matched_spans:
        qty, unit, price = _find_qty(text, span)
        matches = a["matches"]
        ambiguity = None
        if len(matches) > 1:
            ambiguity = {"reason": f"'{a['text']}' matches {len(matches)} products",
                         "candidates": [{"product_id": m["p"], "product_name": m["name"],
                                         "name_hi": m["name_hi"], "emoji": m["emoji"]}
                                        for m in matches[:6]]}
        proposal = {
            "kind": kind_hint, "product_id": matches[0]["p"] if len(matches) == 1 else None,
            "product_name": matches[0]["name"] if len(matches) == 1 else None,
            "qty": qty, "unit": unit, "price_ref_paise": price,
            "confidence": 0.9 if (len(matches) == 1 and qty is not None) else 0.4,
            "ambiguity": ambiguity,
            "question": None,
        }
        if ambiguity:
            proposal["question"] = f"Which one did you mean by '{a['text']}'? / '{a['text']}' से कौन सा उत्पाद है?"
            questions.append(proposal["question"])
        elif qty is None:
            proposal["question"] = f"How many ({a['text']})? / कितने ({a['text']})?"
            questions.append(proposal["question"])
        proposals.append(proposal)

    status = "clarification_needed" if questions else "proposed"
    return {"status": status, "proposals": proposals, "questions": questions, "engine": "rules"}


def _ollama_hint(text: str) -> dict | None:
    """Optional structured extraction via a local Ollama model. Best-effort: any
    failure silently falls back to rules. Output is still proposal-gated."""
    try:
        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/generate",
            data=json.dumps({
                "model": OLLAMA_MODEL, "stream": False, "format": "json",
                "prompt": "Extract product mentions from this Indian shopkeeper message. "
                          "Reply JSON {items:[{name, qty, kind}]}. Message: " + text,
            }).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            return json.loads(data.get("response", "{}"))
    except Exception:
        return None


def parse_capture(conn, text: str) -> dict:
    result = parse_text(conn, text)
    hint = _ollama_hint(text)
    if hint and isinstance(hint.get("items"), list):
        result["engine"] = "ollama+rules"
        result["model_hint"] = hint["items"]
    return result


def confirm_capture(conn, capture_id: int, edits: list[dict], actor: str) -> dict:
    cap = conn.execute("SELECT * FROM captures WHERE id=?", (capture_id,)).fetchone()
    if not cap:
        raise ValueError("capture not found")
    if cap["status"] == "confirmed":
        raise ValueError("capture already confirmed")
    applied = []
    with db.tx(conn):
        for edit in edits:
            idx = edit["index"]
            extracted = db.jload(cap["extracted"], {})
            proposals = extracted.get("proposals", [])
            if idx >= len(proposals):
                continue
            prop = dict(proposals[idx])
            for field in ("product_id", "qty", "kind"):
                if edit.get(field) is not None:
                    prop[field] = edit[field]
            if not prop.get("product_id") or not prop.get("qty"):
                continue
            kind = prop.get("kind", "stock_update")
            if kind == "need":
                cur = conn.execute(
                    "INSERT INTO needs(shop_id, product_id, qty, urgency, alt_product_ids,"
                    " budget_paise, min_shelf_days, status, created_at)"
                    " VALUES (?,?,?, 'normal', '[]', NULL, 14, 'open', ?)",
                    (cap["shop_id"], prop["product_id"], int(prop["qty"]), db.now_iso()))
                applied.append({"type": "need", "need_id": cur.lastrowid,
                                "product_id": prop["product_id"], "qty": int(prop["qty"])})
            else:
                lot = conn.execute(
                    "SELECT id FROM stock_lots WHERE shop_id=? AND product_id=?"
                    " AND expiry_date IS NULL AND condition='sealed' LIMIT 1",
                    (cap["shop_id"], prop["product_id"])).fetchone()
                if lot:
                    conn.execute("UPDATE stock_lots SET qty=qty+?, version=version+1, updated_at=? WHERE id=?",
                                 (int(prop["qty"]), db.now_iso(), lot["id"]))
                    lot_id = lot["id"]
                else:
                    product = conn.execute("SELECT mrp_paise FROM products WHERE id=?",
                                           (prop["product_id"],)).fetchone()
                    cur = conn.execute(
                        "INSERT INTO stock_lots(shop_id, product_id, qty, cost_paise, expiry_date,"
                        " condition, permit_share, slow, retained_floor, version, created_at, updated_at)"
                        " VALUES (?,?,?,? ,NULL,'sealed',1,0,0,1,?,?)",
                        (cap["shop_id"], prop["product_id"], int(prop["qty"]),
                         int((product["mrp_paise"] if product else 1000) * 0.9), db.now_iso(), db.now_iso()))
                    lot_id = cur.lastrowid
                conn.execute(
                    "INSERT INTO inventory_log(shop_id, lot_id, product_id, delta, reason, actor, source, ts)"
                    " VALUES (?,?,?,?, 'capture confirm', ?, 'capture', ?)",
                    (cap["shop_id"], lot_id, prop["product_id"], int(prop["qty"]), actor, db.now_iso()))
                applied.append({"type": "stock_update", "lot_id": lot_id,
                                "product_id": prop["product_id"], "qty": int(prop["qty"])})
        conn.execute("UPDATE captures SET status='confirmed' WHERE id=?", (capture_id,))
        db.log_event(conn, actor, "capture.confirmed", "capture", capture_id, {"applied": applied})
    return {"applied": applied, "capture_status": "confirmed"}
