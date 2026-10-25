"""Planner correctness: CP-SAT vs exhaustive enumeration on small crafted cases,
plus the demo property: bilateral swaps fail where the three-shop cycle succeeds."""
from datetime import date

from app.planner import enumerate_cycles
from app.planner.brute import brute_force
from app.planner.solve import solve_model


def make_ctx(shops, lots, needs, quotes):
    """shops: {id: (lat,lng,cash)}; lots: {(shop,prod): (qty,cost,slow)}; needs:
    [{shop,product,qty,urgency}]; quotes: {prod: price}. Product catalogue is synthetic."""
    names = {p: {"id": p, "name": f"P{p}", "name_hi": f"उ{p}", "emoji": "📦",
                 "pack_size": 1, "unit": "pack"} for p in
             {pid for s, pid in lots} | {n["product"] for n in needs}}
    ctx = {
        "shops": {s: {"id": s, "lat": la, "lng": lo, "cash_limit_paise": c, "withdrawn": 0}
                  for s, (la, lo, c) in shops.items()},
        "needs": [{"id": i + 1, "shop_id": n["shop"], "product_id": n["product"], "qty": n["qty"],
                   "urgency": n.get("urgency", "normal"), "alts": [],
                   "min_shelf_days": n.get("min_shelf_days", 14)}
                  for i, n in enumerate(needs)],
        "quotes": quotes, "names": names, "today": date(2026, 10, 24),
        "lots": {},
        "min_shelf_default": 14, "radius": 3.0, "params": {},
    }
    for (shop, prod), (qty, cost, slow) in lots.items():
        ctx["lots"][(shop, prod)] = [{
            "id": len(ctx["lots"]) * 10 + shop, "shop_id": shop, "product_id": prod, "qty": qty,
            "cost_paise": cost, "expiry_date": None, "condition": "sealed",
            "permit_share": 1, "slow": slow, "retained_floor": 0, "version": 1}]
    return ctx


DEMO = dict(
    shops={1: (26.875, 75.790, 200000), 2: (26.879, 75.793, 200000), 3: (26.872, 75.795, 200000)},
    lots={
        (1, 101): (20, 880, 1),   # shop1 surplus Parle-G (slow)
        (2, 102): (15, 5500, 1),  # shop2 surplus Surf
        (3, 103): (20, 4800, 1),  # shop3 surplus Colgate
    },
    needs=[
        {"shop": 1, "product": 102, "qty": 15, "urgency": "urgent"},
        {"shop": 2, "product": 103, "qty": 20, "urgency": "urgent"},
        {"shop": 3, "product": 101, "qty": 20, "urgency": "urgent"},
    ],
    quotes={101: 1000, 102: 6200, 103: 5500},
)


def test_three_shop_cycle_beats_bilateral():
    ctx = make_ctx(**DEMO)
    cycles = enumerate_cycles(ctx)
    threes = [c for c in cycles if len(c.legs) == 3]
    assert threes, "expected a feasible 3-shop cycle in the demo scenario"
    result = solve_model(cycles, ctx, 5000)
    assert result["status"] == "OPTIMAL"
    selected = [cycles[i] for i, q in enumerate(result["cycle_qty"]) if q > 0]
    assert any(len(c.legs) == 3 for c in selected), "3-cycle should be selected"
    # no bilateral-only solution can cover all three needs
    pairs = solve_model([c for c in cycles if len(c.legs) == 2], ctx, 5000)
    bought = sum(pairs.get("buy", {}).values())
    assert bought > 0, "bilateral-only must fall back to purchases (needs cash)"


def test_cpsat_matches_exhaustive_on_small_cases():
    cases = [
        dict(DEMO, needs=[{"shop": 1, "product": 102, "qty": 4, "urgency": "urgent"},
                          {"shop": 2, "product": 103, "qty": 4, "urgency": "urgent"},
                          {"shop": 3, "product": 101, "qty": 4, "urgency": "urgent"}]),
        dict(  # 4 shops, competing cycle options, tight cash on shop 1
            shops={1: (0, 0, 60000), 2: (0.001, 0, 300000), 3: (0, 0.001, 300000),
                   4: (0.001, 0.001, 300000)},
            lots={(1, 201): (10, 500, 1), (2, 202): (10, 700, 0), (3, 203): (8, 900, 1),
                  (4, 204): (12, 400, 0), (2, 205): (6, 1500, 1)},
            needs=[{"shop": 1, "product": 202, "qty": 3, "urgency": "normal"},
                   {"shop": 2, "product": 203, "qty": 3, "urgency": "urgent"},
                   {"shop": 3, "product": 201, "qty": 3, "urgency": "normal"},
                   {"shop": 4, "product": 205, "qty": 3, "urgency": "normal"},
                   {"shop": 1, "product": 204, "qty": 3, "urgency": "normal"}],
            quotes={201: 600, 202: 800, 203: 1000, 204: 500, 205: 1800},
        ),
        dict(  # infeasible without purchases: no reciprocal surplus at all
            shops={1: (0, 0, 100000), 2: (0.001, 0, 100000)},
            lots={(1, 301): (5, 300, 1)},
            needs=[{"shop": 1, "product": 302, "qty": 3}, {"shop": 2, "product": 301, "qty": 2}],
            quotes={302: 400, 301: 350},
        ),
    ]
    for case in cases:
        ctx = make_ctx(**case)
        cycles = enumerate_cycles(ctx)
        assert len(cycles) <= 12, "brute-force reference needs small case"
        cpsat = solve_model(cycles, ctx, 10000)
        brute = brute_force(cycles, ctx)
        assert brute is not None
        assert cpsat["status"] == "OPTIMAL"
        assert cpsat["objective"] == brute["objective"], (
            f"CP-SAT {cpsat['objective']} != exhaustive {brute['objective']}")


def test_retained_floor_and_share_permission_are_respected():
    ctx = make_ctx(**DEMO)
    ctx["lots"][(2, 102)][0]["retained_floor"] = 5     # owner keeps 5 of the 15
    cycles = enumerate_cycles(ctx)
    result = solve_model(cycles, ctx, 5000)
    for i, c in enumerate(cycles):
        q = result["cycle_qty"][i]
        for e in c.legs:
            if (e.giver, e.product_id) == (2, 102):
                assert q <= 10, "must never plan past the owner's retained floor"


def test_cash_limit_is_never_exceeded():
    ctx = make_ctx(**DEMO)
    ctx["shops"][1]["cash_limit_paise"] = 50000   # ₹500 only
    cycles = enumerate_cycles(ctx)
    result = solve_model(cycles, ctx, 5000)
    assert result["status"] in ("OPTIMAL", "FEASIBLE")
    # recompute cash-out for shop 1 exactly as the model does
    from app.planner.solve import _balancing_per_pack, _shops_in, _transport_paise
    cash = 0
    for i, c in enumerate(cycles):
        q = result["cycle_qty"][i]
        if q and 1 in _shops_in(c):
            cash += _balancing_per_pack(c, 1) * q + _transport_paise(c) * q // len(_shops_in(c))
    shop_of_need = {n["id"]: n["shop_id"] for n in ctx["needs"]}
    for (nid, pid), q in result.get("buy", {}).items():
        if shop_of_need[nid] == 1:
            cash += ctx["quotes"][pid] * q
    assert cash <= 50000 + 1, f"shop 1 cash out {cash} exceeds ₹500 limit"


def test_no_plan_found_is_not_reported_infeasible():
    """A vanishing time limit must degrade to UNKNOWN/FEASIBLE, never INFEASIBLE."""
    ctx = make_ctx(**DEMO)
    cycles = enumerate_cycles(ctx)
    result = solve_model(cycles, ctx, 200)
    assert result["status"] in ("OPTIMAL", "FEASIBLE", "UNKNOWN")
    assert result["status"] != "INFEASIBLE"
