"""Failure rehearsal: operator-only injections (withdraw a participant, shrink stock,
simulate disconnection) that exercise the same production recovery workflow."""
import json

from . import db


def get_state(conn) -> dict:
    state = db.jload(conn.execute("SELECT injections FROM sandbox_state WHERE id=1").fetchone()["injections"], [])
    return {
        "injections": state,
        "withdrawn_shops": [r["id"] for r in conn.execute("SELECT id FROM shops WHERE withdrawn=1")],
        "disconnected_shops": [r["id"] for r in conn.execute("SELECT id FROM shops WHERE disconnected=1")],
    }


def inject(conn, payload: dict, actor: str) -> dict:
    kind = payload.get("type")
    shop_id = payload.get("shop_id")
    if not isinstance(shop_id, int) or isinstance(shop_id, bool):
        raise ValueError("shop_id must identify an existing shop")
    if not conn.execute("SELECT 1 FROM shops WHERE id=?", (shop_id,)).fetchone():
        raise ValueError("shop not found")
    if kind == "withdraw_shop":
        conn.execute("UPDATE shops SET withdrawn=1, version=version+1 WHERE id=?", (shop_id,))
        effect = f"shop {shop_id} withdrawn: it is excluded from planning; plans including it fail revalidation"
    elif kind == "disconnect":
        conn.execute("UPDATE shops SET disconnected=1, version=version+1 WHERE id=?", (shop_id,))
        effect = f"shop {shop_id} disconnected: approvals are blocked and existing plans must be revalidated"
    elif kind == "reduce_stock":
        product_id = payload.get("product_id")
        qty = payload.get("qty", 1)
        if not isinstance(product_id, int) or isinstance(product_id, bool):
            raise ValueError("product_id must identify a product")
        if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
            raise ValueError("qty must be a positive integer number of packs")
        lot = conn.execute(
            "SELECT * FROM stock_lots WHERE shop_id=? AND product_id=? ORDER BY qty DESC LIMIT 1",
            (shop_id, product_id)).fetchone()
        if not lot:
            raise ValueError("no such lot")
        take = min(qty, lot["qty"])
        conn.execute("UPDATE stock_lots SET qty=qty-?, version=version+1, updated_at=? WHERE id=?",
                     (take, db.now_iso(), lot["id"]))
        conn.execute(
            "INSERT INTO inventory_log(shop_id, lot_id, product_id, delta, reason, actor, source, ts)"
            " VALUES (?,?,?,?, 'rehearsal injection', ?, 'sandbox', ?)",
            (shop_id, lot["id"], payload["product_id"], -take, actor, db.now_iso()))
        effect = f"removed {take} units of product {payload['product_id']} from shop {shop_id}"
    else:
        raise ValueError(f"unknown injection type {kind}")
    state = db.jload(conn.execute("SELECT injections FROM sandbox_state WHERE id=1").fetchone()["injections"], [])
    record = {"id": len(state) + 1, **payload, "effect": effect, "at": db.now_iso()}
    state.append(record)
    conn.execute("UPDATE sandbox_state SET injections=? WHERE id=1", (json.dumps(state),))
    db.log_event(conn, actor, "sandbox.injected", "shop", shop_id, record)
    return record


def reset(conn, actor: str) -> dict:
    conn.execute("UPDATE shops SET withdrawn=0, disconnected=0, version=version+1 WHERE withdrawn=1 OR disconnected=1")
    conn.execute("UPDATE sandbox_state SET injections='[]' WHERE id=1")
    db.log_event(conn, actor, "sandbox.reset", None, None, {})
    return {"ok": True}
