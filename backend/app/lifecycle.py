"""Plan lifecycle: PROPOSED → AWAITING_APPROVAL → APPROVED → SANDBOX_DISPATCHED → COMPLETED
with REJECTED / EXPIRED / CANCELLED / NEEDS_OPERATOR. Reservations are the atomicity unit."""
import hashlib
import json
import random
import string
from datetime import datetime, timedelta

from . import db
from .config import RESERVATION_TTL_S
from .planner.graph import days_to_expiry


class Conflict(Exception):
    def __init__(self, msg, status=409):
        super().__init__(msg)
        self.status = status


def inputs_hash(proposal: dict) -> str:
    material = {k: proposal.get(k) for k in
                ("participants", "cycles", "purchases", "coverage", "costs")}
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()[:16]


def create_plan(conn, case_id: str, run_id: int | None, proposal: dict,
                supersedes_id: int | None = None) -> int:
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
    today = today or datetime.utcnow().date()
    lots = [dict(r) for r in conn.execute(
        "SELECT * FROM stock_lots WHERE shop_id=? AND product_id=?", (shop_id, product_id))]
    eligible = []
    for lot in lots:
        if not lot["permit_share"] or lot["condition"] != "sealed":
            continue
        if lot["expiry_date"] and days_to_expiry(lot["expiry_date"], today) < min_shelf_days:
            continue
        eligible.append(lot)
    eligible.sort(key=lambda l: (l["expiry_date"] is None, l["expiry_date"] or ""))
    held = _active_other_reserved(conn, [l["id"] for l in eligible], exclude_plan)
    free_total = 0
    for lot in eligible:
        lot["free"] = max(0, lot["qty"] - lot["retained_floor"] - held.get(lot["id"], 0))
        free_total += lot["free"]
    return free_total, eligible


def submit_for_approval(conn, plan_id: int, actor: str) -> dict:
    """Atomically reserve every leg's stock for RESERVATION_TTL_S, or fail with 409."""
    with db.tx(conn):
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            raise Conflict("plan not found", 404)
        if plan["status"] != "PROPOSED":
            raise Conflict(f"plan is {plan['status']}, not PROPOSED")
        proposal = db.jload(plan["proposal"], {})
        reserved_any = False
        for cycle in proposal.get("cycles", []):
            for leg in cycle.get("legs", []):
                need_qty = leg["qty"]
                free, eligible = fresh_available(conn, leg["from_shop"], leg["product_id"],
                                                 leg.get("min_shelf_days", 14), plan_id)
                if free < need_qty:
                    raise Conflict(
                        f"stock changed: shop {leg['from_shop']} can no longer spare "
                        f"{need_qty} of product {leg['product_id']} (free: {max(0, free)})")
                remaining = need_qty
                for lot in eligible:
                    take = min(remaining, lot.get("free", 0))
                    if take <= 0:
                        continue
                    conn.execute(
                        "INSERT INTO reservations(plan_id, lot_id, qty, expires_at, status, created_at)"
                        " VALUES (?,?,?,?, 'active', ?)",
                        (plan_id, lot["id"], take,
                         (datetime.utcnow() + timedelta(seconds=RESERVATION_TTL_S)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         db.now_iso()))
                    remaining -= take
                    reserved_any = True
                    if remaining == 0:
                        break
        conn.execute("UPDATE plans SET status='AWAITING_APPROVAL', updated_at=? WHERE id=?",
                     (db.now_iso(), plan_id))
        db.log_event(conn, actor, "plan.awaiting_approval", "plan", plan_id,
                     {"version": plan["version"], "ttl_s": RESERVATION_TTL_S,
                      "reserved": reserved_any})
    return {"plan_id": plan_id, "status": "AWAITING_APPROVAL",
            "reservations_expire_at": (datetime.utcnow() + timedelta(seconds=RESERVATION_TTL_S)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def _release(conn, plan_id: int, reason: str):
    conn.execute("UPDATE reservations SET status='released' WHERE plan_id=? AND status='active'",
                 (plan_id,))
    db.log_event(conn, "system", "plan.reservations_released", "plan", plan_id, {"reason": reason})


def approve(conn, plan_id: int, shop_id: int, actor: str) -> dict:
    with db.tx(conn):
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            raise Conflict("plan not found", 404)
        if plan["status"] != "AWAITING_APPROVAL":
            raise Conflict(f"plan is {plan['status']}, not awaiting approval")
        participants = db.jload(plan["participants"], [])
        if shop_id not in participants:
            raise Conflict("shop is not a participant of this plan", 403)
        shop = conn.execute("SELECT disconnected FROM shops WHERE id=?", (shop_id,)).fetchone()
        if shop and shop["disconnected"]:
            raise Conflict("this shop is currently disconnected (simulated); approval not possible", 503)
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
    with db.tx(conn):
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not plan:
            raise Conflict("plan not found", 404)
        if plan["status"] != "AWAITING_APPROVAL":
            raise Conflict(f"plan is {plan['status']}")
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
        if plan["status"] not in ("PROPOSED", "AWAITING_APPROVAL"):
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
    rows = conn.execute(
        "SELECT DISTINCT plan_id FROM reservations WHERE status='active' AND expires_at <= ?",
        (db.now_iso(),)).fetchall()
    for r in rows:
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (r["plan_id"],)).fetchone()
        if plan and plan["status"] == "AWAITING_APPROVAL":
            with db.tx(conn):
                conn.execute("UPDATE plans SET status='EXPIRED', updated_at=? WHERE id=? AND status='AWAITING_APPROVAL'",
                             (db.now_iso(), plan["id"]))
                _release(conn, plan["id"], "approval window lapsed")
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
    today = datetime.utcnow().date()
    for s in proposal.get("participants", []):
        shop = conn.execute("SELECT withdrawn FROM shops WHERE id=?", (s,)).fetchone()
        if not shop:
            problems.append(f"shop {s} no longer exists")
        elif shop["withdrawn"]:
            problems.append(f"shop {s} has withdrawn from the cluster")
    total_needed = {}
    for cycle in proposal.get("cycles", []):
        for leg in cycle.get("legs", []):
            key = (leg["from_shop"], leg["product_id"])
            total_needed[key] = total_needed.get(key, 0) + leg["qty"]
    for (shop_id, product_id), qty in total_needed.items():
        min_shelf = next((leg.get("min_shelf_days", 14)
                          for cycle in proposal.get("cycles", []) for leg in cycle.get("legs", [])
                          if leg["from_shop"] == shop_id and leg["product_id"] == product_id), 14)
        free, _ = fresh_available(conn, shop_id, product_id, min_shelf, plan_id, today)
        if free < qty:
            problems.append(f"shop {shop_id} stock for product {product_id} no longer covers the "
                            f"reserved {qty} (free {max(0, free)})")
    costs = proposal.get("costs", {})
    limits = {r["id"]: r["cash_limit_paise"] for r in conn.execute("SELECT id, cash_limit_paise FROM shops")}
    for s_str, out in costs.get("cash_out_by_shop", {}).items():
        s = int(s_str)
        if s in limits and out > limits[s]:
            problems.append(f"shop {s} cash limit no longer covers its cash outlay")
    return problems


def _ack() -> str:
    return "SL-" + "".join(random.choices(string.digits, k=8))


def dispatch(conn, plan_id: int, actor: str) -> dict:
    """Revalidate, then execute in the labelled sandbox. Any lost/rejected action leaves
    the plan NEEDS_OPERATOR with visible exceptions; nothing silently completes."""
    problems = revalidate(conn, plan_id)
    real_problems = [p for p in problems if not p.startswith("status is")]
    if real_problems:
        with db.tx(conn):
            plan = conn.execute("SELECT status FROM plans WHERE id=?", (plan_id,)).fetchone()
            if plan and plan["status"] != "NEEDS_OPERATOR":
                conn.execute("UPDATE plans SET status='NEEDS_OPERATOR', updated_at=? WHERE id=?",
                             (db.now_iso(), plan_id))
                _release(conn, plan_id, "revalidation failed: " + "; ".join(real_problems)[:200])
            else:
                db.log_event(conn, actor, "plan.revalidation_failed", "plan", plan_id,
                             {"problems": real_problems})
        raise Conflict("revalidation failed: " + "; ".join(problems))
    if problems:   # status-only problem (e.g. dispatch before approval): refuse, no transition
        raise Conflict("revalidation failed: " + "; ".join(problems))

    with db.tx(conn):
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        proposal = db.jload(plan["proposal"], {})
        seq = 0
        outcomes = []
        purchases = {(p["shop_id"], p["product_id"]): p for p in proposal.get("purchases", [])}
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
                    take = min(res["qty"], lot["qty"])
                    if take <= 0:
                        continue
                    conn.execute("UPDATE stock_lots SET qty=qty-?, version=version+1, updated_at=? WHERE id=?",
                                 (take, db.now_iso(), lot["id"]))
                    conn.execute(
                        "INSERT INTO inventory_log(shop_id, lot_id, product_id, delta, reason, actor, source, ts)"
                        " VALUES (?,?,?,?, 'sandbox transfer out', ?, 'sandbox', ?)",
                        (leg["from_shop"], lot["id"], lot["product_id"], -take, actor, db.now_iso()))
                    merge = conn.execute(
                        "SELECT id FROM stock_lots WHERE shop_id=? AND product_id=? AND expiry_date IS ?"
                        " AND condition='sealed' LIMIT 1",
                        (leg["to_shop"], lot["product_id"], lot["expiry_date"])).fetchone()
                    if merge:
                        conn.execute("UPDATE stock_lots SET qty=qty+?, version=version+1, updated_at=? WHERE id=?",
                                     (take, db.now_iso(), merge["id"]))
                    else:
                        conn.execute(
                            "INSERT INTO stock_lots(shop_id, product_id, qty, cost_paise, expiry_date,"
                            " condition, permit_share, slow, retained_floor, version, created_at, updated_at)"
                            " VALUES (?,?,?,?,?,'sealed',0,0,0,1,?,?)",
                            (leg["to_shop"], lot["product_id"], take, leg["unit_value_paise"],
                             lot["expiry_date"], db.now_iso(), db.now_iso()))
                    conn.execute(
                        "INSERT INTO inventory_log(shop_id, lot_id, product_id, delta, reason, actor, source, ts)"
                        " VALUES (?,?,?,?,'sandbox transfer in', ?, 'sandbox', ?)",
                        (leg["to_shop"], None, lot["product_id"], take, actor, db.now_iso()))
                    conn.execute("UPDATE reservations SET status='consumed' WHERE id=?", (res["id"],))
                    moved += take
                status = "acked" if moved == leg["qty"] else "partial"
                result = {"ack": _ack(), "moved": moved, "expected": leg["qty"]}
                conn.execute(
                    "INSERT INTO sandbox_actions(plan_id, seq, kind, payload, status, result, created_at)"
                    " VALUES (?,?, 'transfer', ?, ?, ?, ?)",
                    (plan_id, seq, json.dumps(payload), status, json.dumps(result), db.now_iso()))
                outcomes.append((status, payload))
        for (shop_id, product_id), p in purchases.items():
            seq += 1
            conn.execute(
                "INSERT INTO sandbox_actions(plan_id, seq, kind, payload, status, result, created_at)"
                " VALUES (?,?, 'supplier_order', ?, 'acked', ?, ?)",
                (plan_id, seq, json.dumps({"kind": "supplier_order", "shop_id": shop_id,
                                           "product_id": product_id, "qty": p["qty"],
                                           "price_paise": p["unit_price_paise"]}),
                 json.dumps({"ack": _ack(), "supplier": "sandbox", "eta_days": 2}), db.now_iso()))
            outcomes.append(("acked", {}))

        conn.execute("UPDATE plans SET status='SANDBOX_DISPATCHED', updated_at=? WHERE id=?",
                     (db.now_iso(), plan_id))
        db.log_event(conn, actor, "plan.sandbox_dispatched", "plan", plan_id,
                     {"actions": len(outcomes)})
        # fulfilment: close (or shrink) owner-confirmed needs that the executed plan covered
        for row in proposal.get("coverage", []):
            covered = min(row.get("qty_covered", 0), row.get("qty_needed", 0))
            if covered <= 0:
                continue
            need = conn.execute("SELECT * FROM needs WHERE id=? AND status='open'", (row["need_id"],)).fetchone()
            if not need:
                continue
            if covered >= need["qty"]:
                conn.execute("UPDATE needs SET status='covered' WHERE id=?", (need["id"],))
            else:
                conn.execute("UPDATE needs SET qty=qty-? WHERE id=?", (covered, need["id"]))
            db.log_event(conn, "system", "need.fulfilled", "need", need["id"],
                         {"covered": covered, "plan_id": plan_id})
        failed = [o for o in outcomes if o[0] in ("lost", "rejected", "partial")]
        new_status = "NEEDS_OPERATOR" if failed else "COMPLETED"
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
