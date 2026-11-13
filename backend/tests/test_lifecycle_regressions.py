"""Regression coverage for ownership, elapsed holds and actual sandbox fulfilment."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app import db, lifecycle, sandbox


def make_plan(conn, *, purchases_only=False):
    """Two owners, independently traceable needs and stock, no solver dependency."""
    conn.execute("UPDATE shops SET sharing_opt_in=1 WHERE id IN (1,2)")
    for shop, product in ((1, 1), (2, 2)):
        conn.execute("DELETE FROM stock_lots WHERE shop_id=? AND product_id=?", (shop, product))
        conn.execute(
            "INSERT INTO stock_lots(shop_id,product_id,qty,cost_paise,expiry_date,condition,"
            "permit_share,slow,retained_floor,version,created_at,updated_at) "
            "VALUES (?,?,10,100,'2099-01-01','sealed',1,1,0,1,?,?)",
            (shop, product, db.now_iso(), db.now_iso()))
    needs = []
    for shop, product in ((2, 1), (1, 2)):
        cur = conn.execute(
            "INSERT INTO needs(shop_id,product_id,qty,status,created_at) VALUES (?,?,2,'open',?)",
            (shop, product, db.now_iso()))
        needs.append({"need_id": cur.lastrowid, "shop_id": shop,
                      "product_id": product, "qty_needed": 2, "qty_covered": 2})
    legs = [{"from_shop": 1, "to_shop": 2, "product_id": 1, "qty": 2,
             "unit_value_paise": 100, "need_id": needs[0]["need_id"]},
            {"from_shop": 2, "to_shop": 1, "product_id": 2, "qty": 2,
             "unit_value_paise": 100, "need_id": needs[1]["need_id"]}]
    proposal = {"participants": [1, 2], "cycles": [] if purchases_only else [{"legs": legs}],
                "purchases": ([{"shop_id": 2, "product_id": 1, "qty": 2,
                                "unit_price_paise": 100}] if purchases_only else []),
                "coverage": needs[:1] if purchases_only else needs,
                "costs": {"cash_out_by_shop": {"1": 0, "2": 200 if purchases_only else 0}}}
    plan_id = lifecycle.create_plan(conn, "regression-case", None, proposal)
    lifecycle.submit_for_approval(conn, plan_id, "operator")
    return plan_id, needs


def expire_plan(conn, plan_id):
    conn.execute("UPDATE reservations SET expires_at='2020-01-01T00:00:00Z' WHERE plan_id=?", (plan_id,))
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(plans)")}
    if "approval_expires_at" in columns:
        conn.execute("UPDATE plans SET approval_expires_at='2020-01-01T00:00:00Z' WHERE id=?", (plan_id,))
    conn.execute("UPDATE plans SET updated_at='2020-01-01T00:00:00Z' WHERE id=?", (plan_id,))


def approve_all(conn, plan_id):
    for shop in (1, 2):
        lifecycle.approve(conn, plan_id, shop, f"owner:{shop}")


def test_outsider_cannot_reject_plan(tmp_db):
    with db.connect() as conn:
        plan_id, _ = make_plan(conn)
        with pytest.raises(lifecycle.Conflict) as exc:
            lifecycle.reject(conn, plan_id, 3, "not my plan", "owner:3")
        assert exc.value.status == 403
        assert conn.execute("SELECT status FROM plans WHERE id=?", (plan_id,)).fetchone()[0] == "AWAITING_APPROVAL"


def test_unpriced_lot_is_never_reserved_even_when_it_expires_first(tmp_db):
    with db.connect() as conn:
        plan_id, _ = make_plan(conn)
        conn.execute("UPDATE stock_lots SET expiry_date='2098-01-01' WHERE shop_id=1 AND product_id=1")
        conn.execute(
            "INSERT INTO stock_lots(shop_id,product_id,qty,cost_paise,expiry_date,condition,"
            "permit_share,slow,retained_floor,version,created_at,updated_at) "
            "VALUES (1,1,100,0,'2097-01-01','sealed',1,1,0,1,?,?)",
            (db.now_iso(), db.now_iso()))
        total, eligible = lifecycle.fresh_available(conn, 1, 1, 14, exclude_plan=plan_id)
        assert total == 10
        assert all(lot['cost_paise'] > 0 for lot in eligible)


def test_expired_hold_cannot_be_approved_without_prior_status_read(tmp_db):
    with db.connect() as conn:
        plan_id, _ = make_plan(conn)
        expire_plan(conn, plan_id)
        with pytest.raises(lifecycle.Conflict):
            lifecycle.approve(conn, plan_id, 1, "owner:1")
        assert conn.execute("SELECT COUNT(*) FROM approvals WHERE plan_id=?", (plan_id,)).fetchone()[0] == 0


def test_approved_plan_cannot_dispatch_after_holds_expire(tmp_db):
    with db.connect() as conn:
        plan_id, _ = make_plan(conn)
        approve_all(conn, plan_id)
        expire_plan(conn, plan_id)
        with pytest.raises(lifecycle.Conflict):
            lifecycle.dispatch(conn, plan_id, "operator")
        assert conn.execute("SELECT COUNT(*) FROM sandbox_actions WHERE plan_id=?", (plan_id,)).fetchone()[0] == 0


def test_purchase_only_plan_has_an_approval_deadline(tmp_db):
    with db.connect() as conn:
        plan_id, _ = make_plan(conn, purchases_only=True)
        expire_plan(conn, plan_id)
        lifecycle.sweep_expired(conn)
        assert conn.execute("SELECT status FROM plans WHERE id=?", (plan_id,)).fetchone()[0] == "EXPIRED"


def test_lost_transfer_does_not_fulfil_its_receivers_need(tmp_db):
    with db.connect() as conn:
        plan_id, needs = make_plan(conn)
        approve_all(conn, plan_id)
        conn.execute("UPDATE shops SET disconnected=1 WHERE id=1")
        result = lifecycle.dispatch(conn, plan_id, "operator")
        assert result["status"] == "NEEDS_OPERATOR"
        missed = conn.execute("SELECT status,qty FROM needs WHERE id=?", (needs[0]["need_id"],)).fetchone()
        received = conn.execute("SELECT status FROM needs WHERE id=?", (needs[1]["need_id"],)).fetchone()
        assert missed["status"] == "open" and missed["qty"] == 2
        assert received["status"] == "covered"


def test_supplier_ack_has_real_simulated_receipt_before_need_is_fulfilled(tmp_db):
    with db.connect() as conn:
        plan_id, needs = make_plan(conn, purchases_only=True)
        before = conn.execute("SELECT COALESCE(SUM(qty),0) FROM stock_lots WHERE shop_id=2 AND product_id=1").fetchone()[0]
        approve_all(conn, plan_id)
        lifecycle.dispatch(conn, plan_id, "operator")
        after = conn.execute("SELECT COALESCE(SUM(qty),0) FROM stock_lots WHERE shop_id=2 AND product_id=1").fetchone()[0]
        assert after == before + 2
        assert conn.execute("SELECT status FROM needs WHERE id=?", (needs[0]["need_id"],)).fetchone()[0] == "covered"


def test_cumulative_reserved_cash_cannot_exceed_current_budget(tmp_db):
    with db.connect() as conn:
        conn.execute("UPDATE shops SET cash_limit_paise=250 WHERE id=2")
        first, _ = make_plan(conn, purchases_only=True)
        with pytest.raises(lifecycle.Conflict):
            make_plan(conn, purchases_only=True)
        assert conn.execute("SELECT status FROM plans WHERE id=?", (first,)).fetchone()[0] == "AWAITING_APPROVAL"


def test_completed_purchase_consumes_available_cash(tmp_db):
    with db.connect() as conn:
        plan_id, _ = make_plan(conn, purchases_only=True)
        before = conn.execute("SELECT cash_limit_paise FROM shops WHERE id=2").fetchone()[0]
        approve_all(conn, plan_id)
        lifecycle.dispatch(conn, plan_id, "operator")
        assert conn.execute("SELECT cash_limit_paise FROM shops WHERE id=2").fetchone()[0] == before - 200
        assert conn.execute("SELECT status FROM cash_reservations WHERE plan_id=?", (plan_id,)).fetchone()[0] == "consumed"


def test_material_stock_version_change_requires_a_fresh_plan(tmp_db):
    with db.connect() as conn:
        plan_id, _ = make_plan(conn)
        approve_all(conn, plan_id)
        conn.execute("UPDATE stock_lots SET version=version+1 WHERE shop_id=1 AND product_id=1")
        with pytest.raises(lifecycle.Conflict, match="changed since"):
            lifecycle.dispatch(conn, plan_id, "operator")
        assert conn.execute("SELECT status FROM plans WHERE id=?", (plan_id,)).fetchone()[0] == "NEEDS_OPERATOR"


@pytest.mark.parametrize("qty", [-1, 0, 1.5, True])
def test_rehearsal_rejects_invalid_stock_reduction(tmp_db, qty):
    with db.connect() as conn:
        before = conn.execute("SELECT SUM(qty) FROM stock_lots WHERE shop_id=1 AND product_id=1").fetchone()[0]
        with pytest.raises(ValueError, match="positive integer"):
            sandbox.inject(conn, {"type": "reduce_stock", "shop_id": 1, "product_id": 1, "qty": qty}, "operator")
        after = conn.execute("SELECT SUM(qty) FROM stock_lots WHERE shop_id=1 AND product_id=1").fetchone()[0]
        assert after == before


def test_concurrent_dispatch_executes_once(tmp_db):
    with db.connect() as conn:
        plan_id, _ = make_plan(conn)
        approve_all(conn, plan_id)
    ready = Barrier(2)

    def execute():
        conn = db.connect()
        try:
            ready.wait(timeout=5)
            try:
                return lifecycle.dispatch(conn, plan_id, "operator")["status"]
            except lifecycle.Conflict:
                return "conflict"
        finally:
            conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: execute(), range(2)))
    assert sorted(outcomes) == ["COMPLETED", "conflict"]
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sandbox_actions WHERE plan_id=?", (plan_id,)).fetchone()[0] == 2
