"""HTTP contract regressions for isolation, validated writes and replay safety."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import uuid

import pytest

from app import db, lifecycle
from conftest import auth_headers, login


def owner(client, shop_id=1):
    return auth_headers(login(client, "owner", "1234", shop_id))


def operator(client):
    return auth_headers(login(client, "operator", "0000"))


def proposal_id():
    conn = db.connect()
    try:
        return lifecycle.create_plan(conn, "cluster-main", None,
                                     {"participants": [1], "cycles": [], "purchases": [],
                                      "coverage": [], "costs": {"cash_out_by_shop": {"1": 0}}})
    finally:
        conn.close()


def quantity(conn, shop_id, product_id=1):
    return conn.execute("SELECT COALESCE(SUM(qty),0) FROM stock_lots WHERE shop_id=? AND product_id=?",
                        (shop_id, product_id)).fetchone()[0]


@pytest.mark.parametrize("path", ["stock", "needs", "plans", "pulse", "expiry-actions"])
def test_owner_cannot_read_another_shop(client, path):
    assert client.get(f"/api/shops/2/{path}", headers=owner(client)).status_code == 403


@pytest.mark.parametrize("path", ["summary", "directory", "plans", "events", "export"])
def test_owner_cannot_read_operator_cluster_views(client, path):
    assert client.get(f"/api/cases/cluster-main/{path}", headers=owner(client)).status_code == 403


def test_plan_access_is_limited_to_participants_and_operator(client):
    plan_id = proposal_id()
    for suffix in ("", "/status"):
        assert client.get(f"/api/plans/{plan_id}{suffix}", headers=owner(client, 1)).status_code == 200
        assert client.get(f"/api/plans/{plan_id}{suffix}", headers=owner(client, 2)).status_code == 403
        assert client.get(f"/api/plans/{plan_id}{suffix}", headers=operator(client)).status_code == 200


def test_owner_cannot_submit_dispatch_or_cancel_even_their_own_plan(client):
    plan_id = proposal_id()
    headers = owner(client)
    for action in ("submit", "dispatch", "cancel"):
        assert client.post(f"/api/plans/{plan_id}/{action}", headers=headers).status_code == 403


def test_approval_history_matches_receipt_and_owner_discovery(client):
    plan_id = proposal_id()
    op = operator(client)
    own = owner(client)
    assert client.post(f"/api/plans/{plan_id}/submit", headers=op).status_code == 200
    assert client.post(f"/api/plans/{plan_id}/approve", headers=own).status_code == 200
    receipt = client.get(f"/api/plans/{plan_id}", headers=op).json()
    history = receipt["approval_history"]
    assert history[0]["at"] == history[0]["decided_at"]
    assert history[0]["inputs_hash"] == receipt["inputs_hash"]
    discovered = client.get('/api/shops/1/plans', headers=own).json()
    assert next(p for p in discovered if p['id'] == plan_id)['approval_history'] == history


def test_login_directory_hides_cash_and_private_owner_fields(client):
    public = client.get("/api/shops").json()
    assert public and all("cash_limit_paise" not in row for row in public)
    owners = client.get("/api/shops", headers=owner(client)).json()
    assert "cash_limit_paise" in next(s for s in owners if s["id"] == 1)
    assert all("cash_limit_paise" not in s for s in owners if s["id"] != 1)


@pytest.mark.parametrize("edit", [
    {"product_id": 1, "qty": -1},
    {"product_id": 1, "qty": 1.5},
    {"product_id": 1, "qty": True},
    {"product_id": 1, "qty": 2, "delta": 1},
    {"product_id": 1, "delta": 2},
    {"product_id": 1, "qty": 2, "cost_paise": -1},
    {"product_id": 1, "qty": 2, "retained_floor": 3},
    {"product_id": 1, "qty": 2, "expiry_date": "2026-02-30"},
    {"product_id": 1, "qty": 2, "expiry_date": "not-a-date"},
    {"product_id": 1, "qty": 2, "condition": "unknown"},
])
def test_invalid_inventory_never_changes_stock(client, edit):
    headers = owner(client)
    with db.connect() as conn:
        before = quantity(conn, 1)
    result = client.post("/api/inventory/confirm", json={"shop_id": 1, "changes": [edit]}, headers=headers)
    assert result.status_code == 422, result.text
    with db.connect() as conn:
        assert quantity(conn, 1) == before


def test_existing_lot_requires_version_and_matching_product(client):
    headers = owner(client)
    lot = client.get("/api/shops/1/stock", headers=headers).json()[0]
    edit = {"lot_id": lot["lot_id"], "product_id": lot["product_id"], "qty": lot["qty"] + 1}
    assert client.post("/api/inventory/confirm", json={"shop_id": 1, "changes": [edit]}, headers=headers).status_code == 422
    edit.update(expected_version=lot["version"], product_id=2 if lot["product_id"] != 2 else 1)
    assert client.post("/api/inventory/confirm", json={"shop_id": 1, "changes": [edit]}, headers=headers).status_code == 404


def test_stock_edit_rejects_stale_version(client):
    headers = owner(client)
    lot = client.get("/api/shops/1/stock", headers=headers).json()[0]
    edit = {"lot_id": lot["lot_id"], "product_id": lot["product_id"], "qty": lot["qty"] + 1,
            "expected_version": lot["version"]}
    body = {"shop_id": 1, "changes": [edit]}
    assert client.post("/api/inventory/confirm", json=body, headers=headers).status_code == 200
    assert client.post("/api/inventory/confirm", json=body, headers=headers).status_code == 409


def test_inventory_batch_rolls_back_when_later_edit_is_invalid(client):
    headers = owner(client)
    lot = client.get("/api/shops/1/stock", headers=headers).json()[0]
    with db.connect() as conn:
        before = quantity(conn, 1)
    body = {"shop_id": 1, "changes": [
        {"product_id": 1, "qty": 3},
        {"lot_id": lot["lot_id"], "product_id": lot["product_id"], "delta": -1_000_000,
         "expected_version": lot["version"]}]}
    assert client.post("/api/inventory/confirm", json=body, headers=headers).status_code == 422
    with db.connect() as conn:
        assert quantity(conn, 1) == before


def test_inventory_idempotency_replays_and_rejects_reused_input(client):
    headers = {**owner(client), "Idempotency-Key": uuid.uuid4().hex}
    body = {"shop_id": 1, "changes": [{"product_id": 1, "qty": 3}]}
    with db.connect() as conn:
        before = quantity(conn, 1)
    first = client.post("/api/inventory/confirm", json=body, headers=headers)
    replay = client.post("/api/inventory/confirm", json=body, headers=headers)
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    changed = {"shop_id": 1, "changes": [{"product_id": 1, "qty": 4}]}
    assert client.post("/api/inventory/confirm", json=changed, headers=headers).status_code == 409
    with db.connect() as conn:
        assert quantity(conn, 1) == before + 3


def test_same_idempotency_key_does_not_replay_another_owners_response(client):
    key = uuid.uuid4().hex
    responses = []
    for shop_id in (1, 2):
        headers = {**owner(client, shop_id), "Idempotency-Key": key}
        responses.append(client.post("/api/inventory/confirm",
                                     json={"shop_id": shop_id, "changes": [{"product_id": 1, "qty": 3}]},
                                     headers=headers))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json()["applied"][0]["lot_id"] != responses[1].json()["applied"][0]["lot_id"]


def test_concurrent_same_key_applies_inventory_once(client):
    headers = {**owner(client), "Idempotency-Key": uuid.uuid4().hex}
    body = {"shop_id": 1, "changes": [{"product_id": 1, "qty": 3}]}
    with db.connect() as conn:
        before = quantity(conn, 1)
    barrier = Barrier(2)

    def confirm(_):
        barrier.wait(timeout=5)
        return client.post("/api/inventory/confirm", json=body, headers=headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(confirm, range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json() == responses[1].json()
    with db.connect() as conn:
        assert quantity(conn, 1) == before + 3


def test_owner_cannot_write_another_shops_stock_or_needs(client):
    headers = owner(client)
    assert client.post("/api/inventory/confirm", json={"shop_id": 2, "changes": [{"product_id": 1, "qty": 3}]}, headers=headers).status_code == 403
    assert client.post("/api/needs", json={"shop_id": 2, "product_id": 1, "qty": 3}, headers=headers).status_code == 403


def test_preferences_are_owner_only_and_versioned(client):
    headers = owner(client)
    shop = next(s for s in client.get("/api/shops", headers=headers).json() if s["id"] == 1)
    body = {"expected_version": shop["version"], "cash_limit_paise": 12345, "sharing_opt_in": False}
    assert client.patch("/api/shops/1/preferences", json=body, headers=operator(client)).status_code == 403
    assert client.patch("/api/shops/1/preferences", json=body, headers=owner(client, 2)).status_code == 403
    changed = client.patch("/api/shops/1/preferences", json=body, headers=headers)
    assert changed.status_code == 200, changed.text
    assert changed.json()["cash_limit_paise"] == 12345
    assert changed.json()["version"] == shop["version"] + 1
    assert client.patch("/api/shops/1/preferences", json=body, headers=headers).status_code == 409
    read_back = client.get("/api/shops/1/preferences", headers=headers)
    assert read_back.status_code == 200, read_back.text
    assert read_back.json()["cash_limit_paise"] == 12345
    assert client.get("/api/shops/1/preferences", headers=owner(client, 2)).status_code == 403


@pytest.mark.parametrize("path", ["/api/this-does-not-exist", "/assets/missing-file.js"])
def test_unknown_api_and_assets_do_not_return_spa_html(client, path):
    response = client.get(path)
    assert response.status_code == 404


def test_selected_cluster_scope_contains_only_selected_shops(tmp_db):
    from app.planner import build_context
    with db.connect() as conn:
        context = build_context(conn, {"shop_ids": [1, 2, 3]})
    assert set(context["shops"]) == {1, 2, 3}
    assert all(n["shop_id"] in {1, 2, 3} for n in context["needs"])
    assert all(key[0] in {1, 2, 3} for key in context["lots"])


def test_a_change_during_solving_cannot_be_stamped_as_fresh(client, monkeypatch):
    import app.routes.api as api
    from conftest import run_planner
    real_plan = api.run_plan

    def change_after_solve(ctx, cycles, params):
        result = real_plan(ctx, cycles, params)
        if result.get("participants"):
            with db.connect() as connection:
                with db.tx(connection):
                    connection.execute("UPDATE shops SET version=version+1 WHERE id=?", (result["participants"][0],))
        return result

    monkeypatch.setattr(api, "run_plan", change_after_solve)
    token = login(client, "operator", "0000")
    run = run_planner(client, token, {"shop_ids": [1, 2, 3]})
    assert run["status"] == "done", run
    response = client.post(f"/api/plans/{run['plan_id']}/submit", headers=auth_headers(token))
    assert response.status_code == 409
