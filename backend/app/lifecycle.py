"""Plan lifecycle: PROPOSED → AWAITING_APPROVAL → APPROVED → SANDBOX_DISPATCHED → COMPLETED
with REJECTED / EXPIRED / CANCELLED / NEEDS_OPERATOR. Reservations are the atomicity unit."""
import hashlib
import json
import random
import string
from datetime import datetime, timedelta, timezone

from . import db
from .config import RESERVATION_TTL_S
from .planner.graph import days_to_expiry


class Conflict(Exception):
    def __init__(self, msg, status=409):
        super().__init__(msg)
        self.status = status


def inputs_hash(proposal: dict) -> str:
    material = {k: proposal.get(k) for k in
                ("participants", "cycles", "purchases", "coverage", "costs", "input_versions")}
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()[:16]


def create_plan(conn, case_id: str, run_id: int | None, proposal: dict,
                supersedes_id: int | None = None) -> int:
    proposal = dict(proposal)
    if "input_versions" not in proposal:
        participants = proposal.get("participants", [])
        versions = {"shops": {}, "lots": {}, "needs": {}, "quotes": {}}
        for shop_id in participants:
            shop = conn.execute("SELECT version FROM shops WHERE id=?", (shop_id,)).fetchone()
            if shop:
                versions["shops"][str(shop_id)] = shop["version"]
        for shop_id, product_id in _requirements(proposal):
            for lot in conn.execute("SELECT id,version FROM stock_lots WHERE shop_id=? AND product_id=?",
                                    (shop_id, product_id)):
                versions["lots"][str(lot["id"])] = lot["version"]
        for coverage in proposal.get("coverage", []):
            if coverage.get("qty_covered", 0) > 0:
                need = conn.execute("SELECT * FROM needs WHERE id=?", (coverage["need_id"],)).fetchone()
                if need:
                    versions["needs"][str(need["id"])] = dict(need)
        for purchase in proposal.get("purchases", []):
            quote = conn.execute(
                "SELECT * FROM supplier_quotes WHERE product_id=? AND price_paise=? "
                "AND min_order_packs<=? ORDER BY id LIMIT 1",
                (purchase["product_id"], purchase["unit_price_paise"], purchase["qty"])).fetchone()
            if quote:
                versions["quotes"][str(quote["id"])] = dict(quote)
        proposal["input_versions"] = versions
    version = (conn.execute("SELECT COALESCE(MAX(version),0) v FROM plans WHERE case_id=?",
                            (case_id,)).fetchone()["v"] or 0) + 1
    cur = conn.execute(
        "INSERT INTO plans(case_id, version, run_id, supersedes_id, status, proposal, inputs_hash,"
        " participants, created_at, updated_at) VALUES (?,?,?,?, 'PROPOSED', ?,?,?,?,?)",
        (case_id, version, run_id, supersedes_id, json.dumps(proposal),
         inputs_hash(proposal), json.dumps(proposal.get("participants", [])),
         db.now_iso(), db.now_iso()))
    return cur.lastrowid


def _active_other_reserved(conn, lot_ids: list[int], exclude_plan: int | None) -> dict:
    """lot_id -> qty held by other plans' still-active reservations."""
    if not lot_ids:
        return {}
    q = ",".join("?" * len(lot_ids))
    out = {}
    for row in conn.execute(
            f"SELECT lot_id, SUM(qty) s FROM reservations WHERE lot_id IN ({q})"
            " AND status='active' AND expires_at > ? AND plan_id IS NOT ? GROUP BY lot_id",
            (*lot_ids, db.now_iso(), exclude_plan)):
        out[row["lot_id"]] = row["s"]
    return out


def fresh_available(conn, shop_id: int, product_id: int, min_shelf_days: int,
                    exclude_plan: int | None = None, today=None) -> tuple[int, list[dict]]:
    """Eligible lots ordered FIFO-by-expiry, each with free-after-other-reservations qty;
    plus the total free quantity. This is the single source of availability truth."""
    today = today or datetime.now(timezone.utc).date()
    lots = [dict(r) for r in conn.execute(
        "SELECT * FROM stock_lots WHERE shop_id=? AND product_id=?", (shop_id, product_id))]
    eligible = []
    for lot in lots:
        if not lot["permit_share"] or lot["condition"] != "sealed" or lot["cost_paise"] <= 0:
            continue
        # Unknown/malformed dates are not evidence of adequate remaining shelf life.
        if not lot["expiry_date"]:
            continue
        try:
            if days_to_expiry(lot["expiry_date"], today) < min_shelf_days:
                continue
        except (ValueError, TypeError):
            continue
        eligible.append(lot)
    eligible.sort(key=lambda l: (l["expiry_date"] is None, l["expiry_date"] or ""))
    held = _active_other_reserved(conn, [l["id"] for l in eligible], exclude_plan)
    free_total = 0
    for lot in eligible:
        lot["free"] = max(0, lot["qty"] - lot["retained_floor"] - held.get(lot["id"], 0))
        free_total += lot["free"]
    return free_total, eligible


def _requirements(proposal: dict) -> dict:
    """Aggregate outgoing quantities before reserving; repeated legs cannot reuse a lot."""
    requirements = {}
    for cycle in proposal.get("cycles", []):
        for leg in cycle.get("legs", []):
            key = (leg["from_shop"], leg["product_id"])
            requirement = requirements.setdefault(key, {"qty": 0, "min_shelf_days": 14})
            if not isinstance(leg["qty"], int) or leg["qty"] <= 0:
                raise Conflict("transfer quantities must be positive integer packs")
            requirement["qty"] += leg["qty"]
            requirement["min_shelf_days"] = max(requirement["min_shelf_days"], leg.get("min_shelf_days", 14))
    return requirements


def _deadline_expired(conn, plan) -> bool:
    deadline = plan["approval_expires_at"]
    now = db.now_iso()
    if deadline and deadline <= now:
        return True
    return conn.execute(
        "SELECT 1 FROM reservations WHERE plan_id=? AND status='active' AND expires_at<=? LIMIT 1",
        (plan["id"], now)).fetchone() is not None


def _cash_available(conn, shop_id: int, exclude_plan: int) -> int:
    shop = conn.execute("SELECT cash_limit_paise FROM shops WHERE id=?", (shop_id,)).fetchone()
    if not shop:
        return 0
    held = conn.execute(
        "SELECT COALESCE(SUM(amount_paise),0) FROM cash_reservations WHERE shop_id=? "
        "AND plan_id<>? AND ((status='active' AND expires_at>?) OR status='pending_operator')",
        (shop_id, exclude_plan, db.now_iso())).fetchone()[0]
    return max(0, shop["cash_limit_paise"] - held)


def _proposal_problems(conn, proposal: dict, plan_id: int) -> list[str]:
    problems = []
    participants = proposal.get("participants", [])
    if not participants:
        return ["plan has no participants"]
    for table, group in (("shops", "shops"), ("stock_lots", "lots")):
        for record_id, version in proposal.get("input_versions", {}).get(group, {}).items():
            current = conn.execute(f"SELECT version FROM {table} WHERE id=?", (int(record_id),)).fetchone()
            if not current or current["version"] != version:
                problems.append(f"{group} record {record_id} changed since the plan was prepared")
    for table, group in (("needs", "needs"), ("supplier_quotes", "quotes")):
        for record_id, snapshot in proposal.get("input_versions", {}).get(group, {}).items():
            current = conn.execute(f"SELECT * FROM {table} WHERE id=?", (int(record_id),)).fetchone()
            if not current or dict(current) != snapshot:
                problems.append(f"{group} record {record_id} changed since the plan was prepared")
    for shop_id in participants:
        shop = conn.execute("SELECT withdrawn,sharing_opt_in FROM shops WHERE id=?", (shop_id,)).fetchone()
        if not shop:
            problems.append(f"shop {shop_id} no longer exists")
        elif shop["withdrawn"]:
            problems.append(f"shop {shop_id} has withdrawn from the cluster")
    for (shop_id, product_id), required in _requirements(proposal).items():
        shop = conn.execute("SELECT sharing_opt_in FROM shops WHERE id=?", (shop_id,)).fetchone()
        if not shop or not shop["sharing_opt_in"]:
            problems.append(f"shop {shop_id} has not opted in to sharing")
        free, _ = fresh_available(conn, shop_id, product_id, required["min_shelf_days"], plan_id)
        if free < required["qty"]:
            problems.append(f"shop {shop_id} stock for product {product_id} no longer covers "
                            f"the reserved {required['qty']} (free {free})")
    for shop_string, amount in proposal.get("costs", {}).get("cash_out_by_shop", {}).items():
        shop_id = int(shop_string)
        if not isinstance(amount, int) or amount < 0:
            problems.append(f"shop {shop_id} cash outlay must be nonnegative integer paise")
        elif amount > _cash_available(conn, shop_id, plan_id):
            problems.append(f"shop {shop_id} cash limit no longer covers its cash outlay")
    for coverage in proposal.get("coverage", []):
        if coverage.get("qty_covered", 0) <= 0:
            continue
        need = conn.execute("SELECT qty,status FROM needs WHERE id=?", (coverage["need_id"],)).fetchone()
        if not need or need["status"] != "open" or need["qty"] < coverage["qty_covered"]:
            problems.append(f"need {coverage['need_id']} changed since the plan was prepared")
    return problems


def submit_for_approval(conn, plan_id: int, actor: str) -> dict:
    """Atomically reserve every leg's stock for RESERVATION_TTL_S, or fail with 409."""
    with db.tx(conn):
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            raise Conflict("plan not found", 404)
        if plan["status"] != "PROPOSED":
            raise Conflict(f"plan is {plan['status']}, not PROPOSED")
        proposal = db.jload(plan["proposal"], {})
        problems = _proposal_problems(conn, proposal, plan_id)
        if problems:
            raise Conflict("plan is stale: " + "; ".join(problems))
        deadline = (datetime.now(timezone.utc) + timedelta(seconds=RESERVATION_TTL_S)).strftime("%Y-%m-%dT%H:%M:%SZ")
        reserved_any = False
        for (shop_id, product_id), required in _requirements(proposal).items():
            need_qty = required["qty"]
            free, eligible = fresh_available(conn, shop_id, product_id,
                                             required["min_shelf_days"], plan_id)
            if free < need_qty:
                raise Conflict(
                    f"stock changed: shop {shop_id} can no longer spare "
                    f"{need_qty} of product {product_id} (free: {max(0, free)})")
            remaining = need_qty
            for lot in eligible:
                take = min(remaining, lot.get("free", 0))
                if take <= 0:
                    continue
                conn.execute(
                    "INSERT INTO reservations(plan_id, lot_id, qty, expires_at, status, created_at)"
                    " VALUES (?,?,?,?, 'active', ?)",
                    (plan_id, lot["id"], take, deadline, db.now_iso()))
                remaining -= take
                reserved_any = True
                if remaining == 0:
                    break
        for shop_string, amount in proposal.get("costs", {}).get("cash_out_by_shop", {}).items():
            if amount:
                conn.execute("INSERT INTO cash_reservations(plan_id,shop_id,amount_paise,expires_at) VALUES (?,?,?,?)",
                             (plan_id, int(shop_string), amount, deadline))
        conn.execute("UPDATE plans SET status='AWAITING_APPROVAL', approval_expires_at=?, updated_at=? WHERE id=?",
                     (deadline, db.now_iso(), plan_id))
        db.log_event(conn, actor, "plan.awaiting_approval", "plan", plan_id,
                     {"version": plan["version"], "ttl_s": RESERVATION_TTL_S,
                      "reserved": reserved_any})
    return {"plan_id": plan_id, "status": "AWAITING_APPROVAL",
            "reservations_expire_at": deadline}


def _release(conn, plan_id: int, reason: str):
    conn.execute("UPDATE reservations SET status='released' WHERE plan_id=? AND status='active'",
                 (plan_id,))
    conn.execute("UPDATE cash_reservations SET status='released' WHERE plan_id=? AND status='active'",
                 (plan_id,))
    db.log_event(conn, "system", "plan.reservations_released", "plan", plan_id, {"reason": reason})


def approve(conn, plan_id: int, shop_id: int, actor: str) -> dict:
    sweep_expired(conn)
    with db.tx(conn):
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            raise Conflict("plan not found", 404)
        if plan["status"] != "AWAITING_APPROVAL":
            raise Conflict(f"plan is {plan['status']}, not awaiting approval")
        if _deadline_expired(conn, plan):
            raise Conflict("approval window lapsed")
        participants = db.jload(plan["participants"], [])
        if shop_id not in participants:
            raise Conflict("shop is not a participant of this plan", 403)
        shop = conn.execute("SELECT disconnected,withdrawn FROM shops WHERE id=?", (shop_id,)).fetchone()
        if not shop or shop["withdrawn"]:
            raise Conflict("this shop has withdrawn from the cluster")
        if shop and shop["disconnected"]:
            raise Conflict("this shop is currently disconnected (simulated); approval not possible", 503)
        problems = _proposal_problems(conn, db.jload(plan["proposal"], {}), plan_id)
        if problems:
            raise Conflict("plan changed; request a fresh proposal: " + "; ".join(problems))
        prev = conn.execute("SELECT id FROM approvals WHERE plan_id=? AND shop_id=?",
                            (plan_id, shop_id)).fetchone()
        if prev:
            raise Conflict("this shop has already voted on this plan version")
        conn.execute("INSERT INTO approvals(plan_id, shop_id, decision, decided_at) VALUES (?,?, 'approved', ?)",
                     (plan_id, shop_id, db.now_iso()))
        done = conn.execute("SELECT COUNT(*) c FROM approvals WHERE plan_id=? AND decision='approved'",
                            (plan_id,)).fetchone()["c"]
        if done >= len(participants):
            conn.execute("UPDATE plans SET status='APPROVED', updated_at=? WHERE id=?",
                         (db.now_iso(), plan_id))
        db.log_event(conn, actor, "plan.approved", "plan", plan_id,
                     {"shop_id": shop_id, "all_approved": done >= len(participants)})
    return {"plan_id": plan_id, "approved_by": shop_id,
            "status": "APPROVED" if done >= len(participants) else "AWAITING_APPROVAL"}


def reject(conn, plan_id: int, shop_id: int, reason: str, actor: str) -> dict:
    sweep_expired(conn)
    with db.tx(conn):
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            raise Conflict("plan not found", 404)
        if plan["status"] != "AWAITING_APPROVAL":
            raise Conflict(f"plan is {plan['status']}")
        if shop_id not in db.jload(plan["participants"], []):
            raise Conflict("shop is not a participant of this plan", 403)
        if conn.execute("SELECT 1 FROM approvals WHERE plan_id=? AND shop_id=?", (plan_id, shop_id)).fetchone():
            raise Conflict("this shop has already voted on this plan version")
        conn.execute("INSERT INTO approvals(plan_id, shop_id, decision, reason, decided_at) VALUES (?,?, 'rejected', ?, ?)",
                     (plan_id, shop_id, reason, db.now_iso()))
        conn.execute("UPDATE plans SET status='REJECTED', updated_at=? WHERE id=?",
                     (db.now_iso(), plan_id))
        _release(conn, plan_id, f"rejected by shop {shop_id}")
        db.log_event(conn, actor, "plan.rejected", "plan", plan_id,
                     {"shop_id": shop_id, "reason": reason})
    return {"plan_id": plan_id, "status": "REJECTED"}


def cancel(conn, plan_id: int, actor: str) -> dict:
    with db.tx(conn):
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            raise Conflict("plan not found", 404)
        if plan["status"] not in ("PROPOSED", "AWAITING_APPROVAL", "APPROVED"):
            raise Conflict(f"cannot cancel a plan in status {plan['status']}")
        conn.execute("UPDATE plans SET status='CANCELLED', updated_at=? WHERE id=?",
                     (db.now_iso(), plan_id))
        _release(conn, plan_id, "cancelled by operator")
        db.log_event(conn, actor, "plan.cancelled", "plan", plan_id, {})
    return {"plan_id": plan_id, "status": "CANCELLED"}


def sweep_expired(conn) -> list[int]:
    """Release reservations and expire plans whose approval window lapsed. Called
    opportunistically on reads of planning endpoints."""
    expired_ids = []
    with db.tx(conn):
        rows = conn.execute("SELECT * FROM plans WHERE status IN ('AWAITING_APPROVAL','APPROVED')").fetchall()
        for plan in rows:
            if _deadline_expired(conn, plan):
                conn.execute("UPDATE plans SET status='EXPIRED', updated_at=? WHERE id=?",
                             (db.now_iso(), plan["id"]))
                _release(conn, plan["id"], "approval window lapsed")
                db.log_event(conn, "system", "plan.expired", "plan", plan["id"], {})
                expired_ids.append(plan["id"])
    return expired_ids


def revalidate(conn, plan_id: int) -> list[str]:
    """Pre-dispatch recheck. Returns a list of problems; empty means safe to dispatch."""
    problems = []
    plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    if not plan:
        return ["plan not found"]
    if plan["status"] != "APPROVED":
        problems.append(f"status is {plan['status']}, expected APPROVED")
    proposal = db.jload(plan["proposal"], {})
    if _deadline_expired(conn, plan):
        problems.append("approval window lapsed")
    problems.extend(_proposal_problems(conn, proposal, plan_id))
    for (shop_id, product_id), required in _requirements(proposal).items():
        reserved = conn.execute(
            "SELECT COALESCE(SUM(r.qty),0) FROM reservations r JOIN stock_lots l ON l.id=r.lot_id "
            "WHERE r.plan_id=? AND r.status='active' AND r.expires_at>? AND l.shop_id=? AND l.product_id=?",
            (plan_id, db.now_iso(), shop_id, product_id)).fetchone()[0]
        if reserved != required["qty"]:
            problems.append(f"shop {shop_id} product {product_id} no longer has its exact active reservation")
    return problems


def _ack() -> str:
    return "SL-" + "".join(random.choices(string.digits, k=8))


def _receive_stock(conn, shop_id, product_id, qty, cost_paise, expiry_date, actor, reason):
    """Received stock needs its own sharing consent; never merge it into a shared lot."""
    merge = conn.execute(
        "SELECT id FROM stock_lots WHERE shop_id=? AND product_id=? AND expiry_date IS ? "
        "AND cost_paise=? AND condition='sealed' AND permit_share=0 LIMIT 1",
        (shop_id, product_id, expiry_date, cost_paise)).fetchone()
    if merge:
        lot_id = merge["id"]
        conn.execute("UPDATE stock_lots SET qty=qty+?, version=version+1, updated_at=? WHERE id=?",
                     (qty, db.now_iso(), lot_id))
    else:
        cur = conn.execute(
            "INSERT INTO stock_lots(shop_id,product_id,qty,cost_paise,expiry_date,condition,"
            "permit_share,slow,retained_floor,version,created_at,updated_at) "
            "VALUES (?,?,?,?,?,'sealed',0,0,0,1,?,?)",
            (shop_id, product_id, qty, cost_paise, expiry_date, db.now_iso(), db.now_iso()))
        lot_id = cur.lastrowid
    conn.execute(
        "INSERT INTO inventory_log(shop_id,lot_id,product_id,delta,reason,actor,source,ts) "
        "VALUES (?,?,?,?,?,?,'sandbox',?)",
        (shop_id, lot_id, product_id, qty, reason, actor, db.now_iso()))
    return lot_id


def _dispatch_approved(conn, plan_id: int, actor: str) -> dict:
    """Execute an approved plan while the caller owns the SQLite write lock."""
    plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    proposal = db.jload(plan["proposal"], {})
    seq = 0
    outcomes = []
    delivered_by_need = {}
    unassigned_deliveries = {}
    purchase_spend = {}

    def record_delivery(shop_id, product_id, qty, need_id=None):
        if need_id:
            delivered_by_need[need_id] = delivered_by_need.get(need_id, 0) + qty
        else:
            key = (shop_id, product_id)
            unassigned_deliveries[key] = unassigned_deliveries.get(key, 0) + qty
    # leg -> reservations for this plan on that (giver, product)
    for cycle in proposal.get("cycles", []):
        for leg in cycle.get("legs", []):
            seq += 1
            giver_disc = conn.execute("SELECT disconnected FROM shops WHERE id=?",
                                      (leg["from_shop"],)).fetchone()
            payload = {"kind": "transfer", "from_shop": leg["from_shop"],
                       "to_shop": leg["to_shop"], "product_id": leg["product_id"],
                       "qty": leg["qty"], "unit_value_paise": leg["unit_value_paise"]}
            if giver_disc and giver_disc["disconnected"]:
                conn.execute(
                    "INSERT INTO sandbox_actions(plan_id, seq, kind, payload, status, result, created_at)"
                    " VALUES (?,?, 'transfer', ?, 'lost', ?, ?)",
                    (plan_id, seq, json.dumps(payload),
                     json.dumps({"error": "connection lost during handoff (simulated)"}), db.now_iso()))
                outcomes.append(("lost", payload))
                continue
            # move the reserved stock, lot by lot
            ress = conn.execute(
                "SELECT r.*, l.product_id, l.expiry_date FROM reservations r"
                " JOIN stock_lots l ON l.id = r.lot_id WHERE r.plan_id=? AND r.status='active'"
                " AND l.shop_id=? AND l.product_id=?",
                (plan_id, leg["from_shop"], leg["product_id"])).fetchall()
            moved = 0
            for res in ress:
                lot = conn.execute("SELECT * FROM stock_lots WHERE id=?", (res["lot_id"],)).fetchone()
                take = min(res["qty"], max(0, lot["qty"] - lot["retained_floor"]), leg["qty"] - moved)
                if take <= 0:
                    continue
                conn.execute("UPDATE stock_lots SET qty=qty-?, version=version+1, updated_at=? WHERE id=?",
                             (take, db.now_iso(), lot["id"]))
                conn.execute(
                    "INSERT INTO inventory_log(shop_id, lot_id, product_id, delta, reason, actor, source, ts)"
                    " VALUES (?,?,?,?, 'sandbox transfer out', ?, 'sandbox', ?)",
                    (leg["from_shop"], lot["id"], lot["product_id"], -take, actor, db.now_iso()))
                _receive_stock(conn, leg["to_shop"], lot["product_id"], take, leg["unit_value_paise"],
                               lot["expiry_date"], actor, "sandbox transfer in")
                if take < res["qty"]:
                    conn.execute("UPDATE reservations SET qty=qty-? WHERE id=?", (take, res["id"]))
                    conn.execute(
                        "INSERT INTO reservations(plan_id,lot_id,qty,expires_at,status,created_at) "
                        "VALUES (?,?,?,?,'consumed',?)",
                        (plan_id, lot["id"], take, res["expires_at"], db.now_iso()))
                else:
                    conn.execute("UPDATE reservations SET status='consumed' WHERE id=?", (res["id"],))
                moved += take
                if moved >= leg["qty"]:
                    break
            record_delivery(leg["to_shop"], leg["product_id"], moved, leg.get("need_id"))
            status = "acked" if moved == leg["qty"] else "partial"
            result = {"ack": _ack(), "moved": moved, "expected": leg["qty"]}
            conn.execute(
                "INSERT INTO sandbox_actions(plan_id, seq, kind, payload, status, result, created_at)"
                " VALUES (?,?, 'transfer', ?, ?, ?, ?)",
                (plan_id, seq, json.dumps(payload), status, json.dumps(result), db.now_iso()))
            outcomes.append((status, payload))
    for p in proposal.get("purchases", []):
        shop_id, product_id = p["shop_id"], p["product_id"]
        seq += 1
        _receive_stock(conn, shop_id, product_id, p["qty"], p["unit_price_paise"], None,
                       actor, "simulated supplier delivery")
        record_delivery(shop_id, product_id, p["qty"], p.get("need_id"))
        purchase_spend[shop_id] = purchase_spend.get(shop_id, 0) + p["qty"] * p["unit_price_paise"]
        conn.execute(
            "INSERT INTO sandbox_actions(plan_id, seq, kind, payload, status, result, created_at)"
            " VALUES (?,?, 'supplier_order', ?, 'acked', ?, ?)",
            (plan_id, seq, json.dumps({"kind": "supplier_order", "shop_id": shop_id,
                                       "product_id": product_id, "qty": p["qty"],
                                       "price_paise": p["unit_price_paise"]}),
             json.dumps({"ack": _ack(), "supplier": "sandbox", "eta_days": 0,
                         "simulated_received": True, "delivered_qty": p["qty"],
                         "expiry_date": None}), db.now_iso()))
        outcomes.append(("acked", {}))

    conn.execute("UPDATE plans SET status='SANDBOX_DISPATCHED', updated_at=? WHERE id=?",
                 (db.now_iso(), plan_id))
    db.log_event(conn, actor, "plan.sandbox_dispatched", "plan", plan_id,
                 {"actions": len(outcomes)})
    # fulfilment: close (or shrink) owner-confirmed needs that the executed plan covered
    for row in proposal.get("coverage", []):
        need = conn.execute("SELECT * FROM needs WHERE id=? AND status='open'", (row["need_id"],)).fetchone()
        if not need:
            continue
        actual = delivered_by_need.get(row["need_id"], 0)
        for product_id in [need["product_id"], *db.jload(need["alt_product_ids"], [])]:
            key = (need["shop_id"], product_id)
            used = min(unassigned_deliveries.get(key, 0), max(0, row.get("qty_covered", 0) - actual))
            actual += used
            unassigned_deliveries[key] = unassigned_deliveries.get(key, 0) - used
        covered = min(actual, row.get("qty_covered", 0), need["qty"])
        if covered <= 0:
            continue
        if covered >= need["qty"]:
            conn.execute("UPDATE needs SET status='covered' WHERE id=?", (need["id"],))
        else:
            conn.execute("UPDATE needs SET qty=qty-? WHERE id=?", (covered, need["id"]))
        db.log_event(conn, "system", "need.fulfilled", "need", need["id"],
                     {"covered": covered, "plan_id": plan_id})
    failed = [o for o in outcomes if o[0] in ("lost", "rejected", "partial")]
    new_status = "NEEDS_OPERATOR" if failed else "COMPLETED"
    for shop_string, planned_outlay in proposal.get("costs", {}).get("cash_out_by_shop", {}).items():
        shop_id = int(shop_string)
        # Failed cycles have not completed balancing/transport settlement. Preserve
        # the unspent maximum as a visible operator hold instead of inventing payment.
        spent = min(planned_outlay, purchase_spend.get(shop_id, 0)) if failed else planned_outlay
        if spent:
            conn.execute("UPDATE shops SET cash_limit_paise=cash_limit_paise-?, version=version+1 WHERE id=?",
                         (spent, shop_id))
        remaining = planned_outlay - spent
        conn.execute("UPDATE cash_reservations SET amount_paise=?, status=? WHERE plan_id=? AND shop_id=?",
                     (remaining if failed else planned_outlay,
                      "pending_operator" if failed and remaining else "consumed", plan_id, shop_id))
        db.log_event(conn, "system", "sandbox.cash_accounted", "shop", shop_id,
                     {"plan_id": plan_id, "spent_paise": spent,
                      "held_for_operator_paise": remaining if failed else 0, "simulated": True})
    conn.execute("UPDATE plans SET status=?, updated_at=? WHERE id=?",
                 (new_status, db.now_iso(), plan_id))
    if new_status == "COMPLETED":
        db.log_event(conn, "system", "plan.completed", "plan", plan_id, {})
    else:
        conn.execute("UPDATE reservations SET status='released' WHERE plan_id=? AND status='active'",
                     (plan_id,))
        db.log_event(conn, "system", "plan.needs_operator", "plan", plan_id,
                     {"failed_actions": [p for _s, p in failed]})
    return {"plan_id": plan_id, "status": new_status, "exceptions": len(failed)}


def dispatch(conn, plan_id: int, actor: str) -> dict:
    """Revalidate and execute under one lock; concurrent dispatch cannot run twice."""
    sweep_expired(conn)
    failure = None
    result = None
    with db.tx(conn):
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            raise Conflict("plan not found", 404)
        if plan["status"] not in ("APPROVED", "AWAITING_APPROVAL"):
            raise Conflict(f"cannot dispatch a plan in status {plan['status']}")
        problems = revalidate(conn, plan_id)
        if problems:
            material = [p for p in problems if not p.startswith("status is")]
            if material:
                conn.execute("UPDATE plans SET status='NEEDS_OPERATOR', updated_at=? WHERE id=?",
                             (db.now_iso(), plan_id))
                _release(conn, plan_id, "revalidation failed")
                db.log_event(conn, actor, "plan.revalidation_failed", "plan", plan_id,
                             {"problems": material})
            failure = "revalidation failed: " + "; ".join(problems)
        else:
            result = _dispatch_approved(conn, plan_id, actor)
    if failure:
        raise Conflict(failure)
    return result
