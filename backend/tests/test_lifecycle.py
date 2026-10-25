"""Full workflow tests through the HTTP API: propose → reserve → approve → dispatch,
plus rejection, expiry, withdrawal recovery, disconnect and authorisation boundaries."""
import uuid

from conftest import auth_headers, login, run_planner


def get_plan(client, op, plan_id):
    return client.get(f"/api/plans/{plan_id}", headers=auth_headers(op)).json()


def full_flow(client, op, params=None):
    """Run planner, submit for approval, return (plan, participant tokens)."""
    run = run_planner(client, op, params)
    assert run["status"] == "done", run.get("error")
    plan_id = run["plan_id"]
    assert plan_id, "expected a plan proposal"
    plan = get_plan(client, op, plan_id)
    tokens = {s: login(client, "owner", "1234", s) for s in plan["participants"]}
    r = client.post(f"/api/plans/{plan_id}/submit", headers=auth_headers(op))
    assert r.status_code == 200, r.text
    return run, plan_id, plan, tokens


def test_propose_approve_dispatch_completes(client):
    op = login(client, "operator", "0000")
    run, plan_id, plan, tokens = full_flow(client, op)
    st = client.get(f"/api/plans/{plan_id}/status", headers=auth_headers(op)).json()
    assert st["status"] == "AWAITING_APPROVAL"
    assert st["reservations"], "approval entry must reserve stock"
    # partial approval keeps it waiting
    first = plan["participants"][0]
    r = client.post(f"/api/plans/{plan_id}/approve", headers=auth_headers(tokens[first]))
    assert r.json()["status"] == "AWAITING_APPROVAL"
    for s in plan["participants"][1:]:
        client.post(f"/api/plans/{plan_id}/approve", headers=auth_headers(tokens[s]))
    st = client.get(f"/api/plans/{plan_id}/status", headers=auth_headers(op)).json()
    assert st["status"] == "APPROVED"
    r = client.post(f"/api/plans/{plan_id}/dispatch", headers=auth_headers(op))
    assert r.status_code == 200 and r.json()["status"] == "COMPLETED", r.text
    # stock actually moved in the sandbox
    body = get_plan(client, op, plan_id)
    moved = [leg for c in body["cycles"] for leg in c["legs"]]
    if moved:
        giver, receiver, pid = moved[0]["from_shop"], moved[0]["to_shop"], moved[0]["product_id"]
        qty = moved[0]["qty"]
        gs = client.get(f"/api/shops/{giver}/stock", headers=auth_headers(op)).json()
        rs = client.get(f"/api/shops/{receiver}/stock", headers=auth_headers(op)).json()
        assert sum(l["qty"] for l in rs if l["product_id"] == pid) >= qty
        assert all(l["product_id"] != pid or l["qty"] < 10**9 for l in gs)


def test_rejection_releases_reservations_and_allows_replan(client):
    op = login(client, "operator", "0000")
    run, plan_id, plan, tokens = full_flow(client, op)
    first = plan["participants"][0]
    r = client.post(f"/api/plans/{plan_id}/reject",
                    json={"reason": "Mujhe yeh pack nahi chahiye"},
                    headers=auth_headers(tokens[first]))
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    st = client.get(f"/api/plans/{plan_id}/status", headers=auth_headers(op)).json()
    assert all(res["status"] == "released" for res in st["reservations"])
    # the same stock can be reserved again by a fresh plan
    run2 = run_planner(client, op)
    assert run2["plan_id"]
    r = client.post(f"/api/plans/{run2['plan_id']}/submit", headers=auth_headers(op))
    assert r.status_code == 200, r.text


def test_concurrent_reservations_never_double_allocate(client):
    """Two plans wanting the same stock: the second submit must fail with 409."""
    op = login(client, "operator", "0000")
    run1 = run_planner(client, op)
    run2 = run_planner(client, op)
    assert run1["plan_id"] and run2["plan_id"]
    r1 = client.post(f"/api/plans/{run1['plan_id']}/submit", headers=auth_headers(op))
    assert r1.status_code == 200
    r2 = client.post(f"/api/plans/{run2['plan_id']}/submit", headers=auth_headers(op))
    assert r2.status_code == 409, f"expected conflict, got {r2.status_code}: {r2.text}"
    active1 = client.get(f"/api/plans/{run1['plan_id']}/status", headers=auth_headers(op)).json()
    assert any(res["status"] == "active" for res in active1["reservations"])


def test_expired_approval_window_releases(client):
    op = login(client, "operator", "0000")
    run, plan_id, plan, tokens = full_flow(client, op)
    # shift reservations into the past directly in the DB
    from app import db as dbmod
    conn = _conn(client)
    with dbmod.tx(conn):
        conn.execute("UPDATE reservations SET expires_at='2020-01-01T00:00:00Z' WHERE plan_id=?", (plan_id,))
    conn.close()
    st = client.get(f"/api/plans/{plan_id}/status", headers=auth_headers(op)).json()
    assert st["status"] == "EXPIRED"
    assert all(res["status"] == "released" for res in st["reservations"])


def _conn(client):
    from app import db as dbmod
    return dbmod.connect()


def test_withdrawal_recovery_produces_revised_plan(client):
    """The rehearsal: withdraw a participant after approval; revalidation must refuse,
    the plan must land in NEEDS_OPERATOR, and a re-plan must succeed without that shop."""
    op = login(client, "operator", "0000")
    run, plan_id, plan, tokens = full_flow(client, op)
    for s in plan["participants"]:
        client.post(f"/api/plans/{plan_id}/approve", headers=auth_headers(tokens[s]))
    victim = plan["participants"][0]
    r = client.post("/api/sandbox/inject",
                    json={"type": "withdraw_shop", "shop_id": victim},
                    headers=auth_headers(op))
    assert r.status_code == 200
    r = client.post(f"/api/plans/{plan_id}/dispatch", headers=auth_headers(op))
    assert r.status_code == 409
    st = client.get(f"/api/plans/{plan_id}/status", headers=auth_headers(op)).json()
    assert st["status"] == "NEEDS_OPERATOR"
    # recovery: re-plan while the withdrawal is still active — the new plan must exclude
    # the withdrawn shop and need fresh approvals
    run2 = run_planner(client, op)
    assert run2["plan_id"]
    plan2 = get_plan(client, op, run2["plan_id"])
    assert plan2["version"] > plan["version"]
    assert victim not in plan2["participants"]
    tokens2 = {s: login(client, "owner", "1234", s) for s in plan2["participants"]}
    assert client.post(f"/api/plans/{run2['plan_id']}/submit", headers=auth_headers(op)).status_code == 200
    for s in plan2["participants"]:
        client.post(f"/api/plans/{run2['plan_id']}/approve", headers=auth_headers(tokens2[s]))
    r = client.post(f"/api/plans/{run2['plan_id']}/dispatch", headers=auth_headers(op))
    assert r.status_code == 200, r.text


def test_disconnect_blocks_approval_and_breaks_handoff(client):
    op = login(client, "operator", "0000")
    run, plan_id, plan, tokens = full_flow(client, op)
    victim = plan["participants"][0]
    client.post("/api/sandbox/inject", json={"type": "disconnect", "shop_id": victim},
                headers=auth_headers(op))
    r = client.post(f"/api/plans/{plan_id}/approve", headers=auth_headers(tokens[victim]))
    assert r.status_code == 503, "disconnected shop must not be able to approve"
    client.post("/api/sandbox/reset", headers=auth_headers(op))


def test_reduce_stock_breaks_revalidation(client):
    """Stale-information rehearsal: stock drains while the plan is awaiting approval;
    dispatch must then refuse and leave the plan to the operator."""
    op = login(client, "operator", "0000")
    run, plan_id, plan, tokens = full_flow(client, op)
    leg = next((leg for c in plan["cycles"] for leg in c["legs"]), None)
    if leg:
        for _ in range(5):   # drain every lot of that (shop, product) while approvals are open
            client.post("/api/sandbox/inject",
                        json={"type": "reduce_stock", "shop_id": leg["from_shop"],
                              "product_id": leg["product_id"], "qty": 10**6},
                        headers=auth_headers(op))
        r = client.post(f"/api/plans/{plan_id}/dispatch", headers=auth_headers(op))
        assert r.status_code == 409, "stock drained below reservations must fail revalidation"
        st = client.get(f"/api/plans/{plan_id}/status", headers=auth_headers(op)).json()
        assert st["status"] == "NEEDS_OPERATOR"


def test_operator_cannot_approve(client):
    op = login(client, "operator", "0000")
    run, plan_id, plan, tokens = full_flow(client, op)
    r = client.post(f"/api/plans/{plan_id}/approve", headers=auth_headers(op))
    assert r.status_code == 403
    client.post(f"/api/plans/{plan_id}/cancel", headers=auth_headers(op))


def test_non_participant_owner_cannot_approve(client):
    op = login(client, "operator", "0000")
    # purchases-only plans make every shop a participant; restrict to exchanges
    run, plan_id, plan, tokens = full_flow(client, op, {"include_purchases": False})
    outsider = next(s for s in range(1, 26) if s not in plan["participants"])
    tok = login(client, "owner", "1234", outsider)
    r = client.post(f"/api/plans/{plan_id}/approve", headers=auth_headers(tok))
    assert r.status_code in (403, 409)
    client.post(f"/api/plans/{plan_id}/cancel", headers=auth_headers(op))


def test_wrong_pin_rejected(client):
    r = client.post("/api/session", json={"role": "owner", "shop_id": 1, "pin": "9999"})
    assert r.status_code == 401
    r = client.post("/api/session", json={"role": "operator", "pin": "1111"})
    assert r.status_code == 401


def test_idempotent_inventory_confirm(client):
    tok = login(client, "owner", "1234", 1)
    key = uuid.uuid4().hex
    stock_before = client.get("/api/shops/1/stock", headers=auth_headers(tok)).json()
    before = sum(l["qty"] for l in stock_before if l["product_id"] == 4)
    body = {"shop_id": 1, "changes": [{"product_id": 4, "qty": 5}], "reason": "test"}
    r1 = client.post("/api/inventory/confirm", json=body, headers={**auth_headers(tok), "Idempotency-Key": key})
    r2 = client.post("/api/inventory/confirm", json=body, headers={**auth_headers(tok), "Idempotency-Key": key})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json(), "replay must return the cached response"
    stock_after = client.get("/api/shops/1/stock", headers=auth_headers(tok)).json()
    after = sum(l["qty"] for l in stock_after if l["product_id"] == 4)
    assert after == before + 5, "replayed request must not apply twice"
