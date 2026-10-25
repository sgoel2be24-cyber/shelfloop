import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app.db as appdb            # noqa: E402
from app import seed              # noqa: E402


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setattr(appdb, "DB_PATH", p)
    seed.seed(db_path=p, force=True)
    return p


@pytest.fixture()
def client(tmp_db, monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main_mod
    with TestClient(main_mod.app) as c:
        yield c


def login(client, role, pin, shop_id=None):
    body = {"role": role, "pin": pin}
    if shop_id is not None:
        body["shop_id"] = shop_id
    r = client.post("/api/session", json=body)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def run_planner(client, op_token, params=None):
    r = client.post("/api/planning-runs", json={"case_id": "cluster-main", "params": params or {}},
                    headers=auth_headers(op_token))
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    for _ in range(200):
        r = client.get(f"/api/planning-runs/{run_id}", headers=auth_headers(op_token))
        assert r.status_code == 200
        if r.json()["status"] in ("done", "error"):
            return r.json()
        import time
        time.sleep(0.05)
    raise AssertionError("planning run did not finish")
