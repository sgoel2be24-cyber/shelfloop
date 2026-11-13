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
            "cost_paise": cost, "expiry_date": "2027-12-31", "condition": "sealed",
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
        assert cpsat["objective_vector"] == brute["objective_vector"], (
            f"CP-SAT {cpsat['objective_vector']} != exhaustive {brute['objective_vector']}")


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
    from app.planner.solve import _shops_in, cycle_cash_out
    cash = 0
    for i, c in enumerate(cycles):
        q = result["cycle_qty"][i]
        if q and 1 in _shops_in(c):
            cash += cycle_cash_out(c, q)[1]
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


def test_expensive_affordable_need_still_has_coverage_priority():
    ctx = make_ctx({1: (0, 0, 3_000_000)}, {},
                   [{"shop": 1, "product": 1, "qty": 1}], {1: 2_000_000})
    result = solve_model([], ctx, 1000)
    assert result.get("buy", {}).get((1, 1)) == 1


def test_slow_stock_bonus_cannot_make_a_more_expensive_plan_win():
    ctx = make_ctx({1: (0, 0, 100000), 2: (0, 0, 100000)},
                   {(1, 1): (1, 100, 1), (2, 2): (1, 100, 1)},
                   [{"shop": 1, "product": 2, "qty": 1},
                    {"shop": 2, "product": 1, "qty": 1}], {1: 2400, 2: 2400})
    result = solve_model(enumerate_cycles(ctx), ctx, 1000)
    assert sum(result.get("buy", {}).values()) == 2
    assert not any(result["cycle_qty"])


def test_receiving_balancing_cash_does_not_finance_purchases():
    from app.planner.solve import plan
    ctx = make_ctx({1: (0, 0, 20000), 2: (0, 0, 200000)},
                   {(1, 1): (1, 100000, 1), (2, 2): (1, 1000, 1)},
                   [{"shop": 1, "product": 2, "qty": 1},
                    {"shop": 2, "product": 1, "qty": 1},
                    {"shop": 1, "product": 3, "qty": 1}], {1: 100000, 2: 1000, 3: 100000})
    proposal = plan(ctx, enumerate_cycles(ctx), {"time_limit_ms": 1000})
    for sid, cash in proposal["costs"]["cash_out_by_shop"].items():
        assert cash <= ctx["shops"][int(sid)]["cash_limit_paise"]


def test_no_overdelivery_of_a_need():
    # Supplier pack costs less than cycle transport, but secondary slow-stock
    # incentives must not allow filling the same confirmed need twice.
    ctx = make_ctx(**DEMO)
    ctx["needs"] = [{**n, "qty": 1} for n in ctx["needs"]]
    ctx["quotes"] = {pid: 1 for pid in ctx["quotes"]}
    result = solve_model(enumerate_cycles(ctx), ctx, 1000)
    covered = {n["id"]: 0 for n in ctx["needs"]}
    cycles = enumerate_cycles(ctx)
    for cycle, qty in zip(cycles, result["cycle_qty"]):
        for leg in cycle.legs:
            covered[leg.need_id] += qty
    for (nid, _), qty in result["buy"].items():
        covered[nid] += qty
    assert all(covered[n["id"]] <= n["qty"] for n in ctx["needs"])


def test_transport_callout_is_once_and_every_paise_is_allocated():
    from app.planner.solve import cycle_transport_paise, cycle_transport_shares
    from app.config import TRANSPORT_BASE_PAISE
    ctx = make_ctx(**DEMO)
    cycle = enumerate_cycles(ctx)[0]
    one, seven = cycle_transport_paise(cycle, 1), cycle_transport_paise(cycle, 7)
    assert seven == TRANSPORT_BASE_PAISE + (one - TRANSPORT_BASE_PAISE) * 7
    shares = cycle_transport_shares(cycle, 7)
    assert sum(shares.values()) == seven
    # Each component is apportioned in integer paise; no remainder disappears.
    assert max(shares.values()) - min(shares.values()) <= 8
    assert sum(cycle_transport_shares(cycle, 0).values()) == 0


def test_quote_minimum_order_selects_an_eligible_supplier():
    ctx = make_ctx({1: (0, 0, 2000)}, {}, [{"shop": 1, "product": 1, "qty": 2}], {1: 100})
    ctx["quote_options"] = {1: [{"price_paise": 100, "min_order_packs": 10},
                               {"price_paise": 800, "min_order_packs": 1}]}
    result = solve_model([], ctx, 1000)
    assert result["buy"] == {(1, 1): 2}
    assert result["buy_prices"] == {(1, 1): 800}
    assert result["objective_vector"][1] == -1600


def test_unknown_or_expired_dates_are_not_shared():
    for invalid in (None, "not-a-date", "2026-10-25"):
        ctx = make_ctx(**DEMO)
        ctx["lots"][(1, 101)][0]["expiry_date"] = invalid
        assert not enumerate_cycles(ctx), invalid


def test_shop_opt_out_and_existing_reservations_are_respected():
    ctx = make_ctx(**DEMO)
    ctx["shops"][1]["sharing_opt_in"] = 0
    assert not enumerate_cycles(ctx)
    ctx = make_ctx(**DEMO)
    ctx["lots"][(1, 101)][0]["reserved_qty"] = 20
    assert not enumerate_cycles(ctx)


def test_candidate_limit_is_enforced_and_reported(monkeypatch):
    import app.planner.graph as graph
    ctx = make_ctx(**DEMO)
    monkeypatch.setattr(graph, "MAX_CYCLES", 1)
    assert len(enumerate_cycles(ctx)) == 1
    assert ctx["candidate_truncated"]


def test_zero_deadline_does_not_claim_infeasibility_or_optimality():
    result = solve_model([], make_ctx(**DEMO), 0)
    assert result["status"] == "UNKNOWN"
    assert result["objective"] is None
    assert not result["proven_optimal"]


def test_twenty_random_small_cases_match_all_exhaustive_objectives():
    import random
    rng = random.Random(20261025)
    for _ in range(20):
        ctx = make_ctx(
            {s: (0, 0, rng.randrange(1, 12) * 2000) for s in (1, 2, 3)},
            {(s, s): (3, rng.randrange(100, 5000), rng.randrange(2)) for s in (1, 2, 3)},
            [{"shop": s, "product": s % 3 + 1, "qty": rng.randrange(1, 4),
              "urgency": rng.choice(["urgent", "normal"])} for s in (1, 2, 3)],
            {p: rng.randrange(100, 5000) for p in (1, 2, 3)})
        cycles = enumerate_cycles(ctx)
        solved = solve_model(cycles, ctx, 1000)
        brute = brute_force(cycles, ctx)
        assert solved["status"] == "OPTIMAL"
        assert solved["objective_vector"] == brute["objective_vector"]


def test_receipt_totals_match_solver_budget_vector():
    from app.planner.solve import plan
    ctx = make_ctx(**DEMO)
    receipt = plan(ctx, enumerate_cycles(ctx), {"time_limit_ms": 1000})
    costs = receipt["costs"]
    assert costs["gross_cash_out_paise"] == sum(costs["cash_out_by_shop"].values())
    assert -receipt["solver"]["objective_vector"][1] == costs["gross_cash_out_paise"]
    assert costs["gross_cash_out_paise"] == costs["external_cash_paise"] + costs["balancing_cash_paise"]
    assert costs["transport_paise"] == sum(c["transport_paise"] for c in receipt["cycles"])
    for cycle in receipt["cycles"]:
        assert cycle["transport_paise"] == sum(cycle["transport_by_shop_paise"].values())
        assert all("need_id" in leg for leg in cycle["legs"])
