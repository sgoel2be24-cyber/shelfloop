"""Capture pipeline: ambiguity must clarify, never commit; bilingual input parses;
confirmation applies exactly the edited records."""
from conftest import auth_headers, login


def test_ambiguous_phrase_needs_clarification(client):
    tok = login(client, "owner", "1234", 1)
    r = client.post("/api/captures", json={"shop_id": 1, "text": "₹10 wala biscuit"},
                    headers=auth_headers(tok))
    body = r.json()
    assert body["status"] == "clarification_needed", body
    prop = body["proposals"][0]
    assert prop["ambiguity"] and len(prop["ambiguity"]["candidates"]) >= 2
    assert prop["product_id"] is None, "ambiguous product must not be pre-selected as final"
    st = client.get("/api/shops/1/stock", headers=auth_headers(tok)).json()
    before = sum(l["qty"] for l in st)
    r = client.post(f"/api/captures/{body['capture_id']}/confirm", json={"edits": []},
                    headers={**auth_headers(tok), "Idempotency-Key": "amb-1"})
    st2 = client.get("/api/shops/1/stock", headers=auth_headers(tok)).json()
    assert sum(l["qty"] for l in st2) == before, "unresolved capture must commit nothing"


def test_hindi_and_codeswitched_capture_parses(client):
    tok = login(client, "owner", "1234", 1)
    r = client.post("/api/captures", json={"shop_id": 1, "text": "mujhe surf excel 5 packet chahiye"},
                    headers=auth_headers(tok))
    body = r.json()
    assert body["status"] in ("proposed", "clarification_needed")
    prop = body["proposals"][0]
    assert prop["kind"] == "need"
    assert prop["qty"] == 5
    # owner resolves any ambiguity explicitly; "surf" matches several Surf SKUs
    pid = prop["product_id"] or prop["ambiguity"]["candidates"][0]["product_id"]
    edits = [{"index": 0, "product_id": pid, "qty": 5, "kind": "need"}]
    r = client.post(f"/api/captures/{body['capture_id']}/confirm", json={"edits": edits},
                    headers={**auth_headers(tok), "Idempotency-Key": "hi-1"})
    assert r.status_code == 200 and r.json()["applied"], r.text
    needs = client.get("/api/shops/1/needs", headers=auth_headers(tok)).json()
    assert any(n["product_id"] == pid and n["qty"] == 5 for n in needs)


def test_hindi_stock_update(client):
    tok = login(client, "owner", "1234", 2)
    r = client.post("/api/captures", json={"shop_id": 2, "text": "maggi 12 packet aa gaya hai"},
                    headers=auth_headers(tok))
    body = r.json()
    assert body["status"] in ("proposed", "clarification_needed")
    prop = body["proposals"][0]
    assert prop["kind"] == "stock_update" and prop["qty"] == 12
    pid = prop["product_id"] or prop["ambiguity"]["candidates"][0]["product_id"]
    edits = [{"index": 0, "product_id": pid, "qty": 12, "kind": "stock_update"}]
    r = client.post(f"/api/captures/{body['capture_id']}/confirm", json={"edits": edits},
                    headers={**auth_headers(tok), "Idempotency-Key": "hi-2"})
    assert r.status_code == 200
    stock = client.get("/api/shops/2/stock", headers=auth_headers(tok)).json()
    assert any(l["product_id"] == pid for l in stock), "lot should exist after stock update"


def test_unknown_product_fails_gracefully(client):
    tok = login(client, "owner", "1234", 1)
    r = client.post("/api/captures", json={"shop_id": 1, "text": "xyzabc 5 packet"},
                    headers=auth_headers(tok))
    assert r.json()["status"] == "failed"
    assert r.json()["questions"]


def test_owner_isolated_to_own_shop(client):
    tok = login(client, "owner", "1234", 1)
    r = client.post("/api/captures", json={"shop_id": 2, "text": "maggi 5 packet"},
                    headers=auth_headers(tok))
    assert r.status_code == 403
    r = client.get("/api/shops/2/stock", headers=auth_headers(tok))
    assert r.status_code == 200  # reads of other shops' shared surplus are allowed
