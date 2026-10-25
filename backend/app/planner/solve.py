"""CP-SAT planner. Objective priority (encoded by weights, integer paise throughout):
1. maximise coverage of owner-confirmed needs (urgent counts double)
2. minimise additional cash: purchases + known transaction/transport costs
3. prefer redeploying explicitly marked slow stock
4. minimise transport burden
Solver status is reported verbatim: a timeout is FEASIBLE/UNKNOWN, never 'infeasible'."""
import time

from ortools.sat.python import cp_model

from ..config import (COVERAGE_WEIGHT, DEFAULT_TIME_LIMIT_MS, SLOW_REDEPLOY_BONUS_PAISE,
                      TRANSPORT_BASE_PAISE, TRANSPORT_RATE_PAISE_PER_PACK_KM, URGENCY_WEIGHTS)
from .graph import Cycle


def _balancing_per_pack(cycle: Cycle, shop_id: int) -> int:
    """value received − value given, per pack, for one participant of one cycle."""
    vin = sum(e.unit_value_paise for e in cycle.legs if e.receiver == shop_id)
    vout = sum(e.unit_value_paise for e in cycle.legs if e.giver == shop_id)
    return vin - vout


def _transport_paise(cycle: Cycle) -> int:
    dist = sum(e.dist_km for e in cycle.legs)
    return TRANSPORT_BASE_PAISE + int(TRANSPORT_RATE_PAISE_PER_PACK_KM * dist)


def _shops_in(cycle: Cycle) -> set:
    return {e.giver for e in cycle.legs} | {e.receiver for e in cycle.legs}


def solve_model(cycles: list, ctx: dict, time_limit_ms: int, collect_solution: bool = True,
                allow_purchases: bool = True) -> dict:
    """One CP-SAT instance. Returns status, objective and (when feasible) the chosen
    per-cycle quantities and purchase quantities keyed by (need_id, product_id)."""
    model = cp_model.CpModel()
    qty = [model.NewIntVar(0, c.max_qty, f"q{i}") for i, c in enumerate(cycles)]
    sel = [model.NewBoolVar(f"s{i}") for i, c in enumerate(cycles)]
    for i, c in enumerate(cycles):
        model.Add(qty[i] <= c.max_qty * sel[i])
        model.Add(sel[i] <= qty[i])

    needs = {n["id"]: n for n in ctx["needs"]}
    purchasable = {}   # (need_id, product_id) -> best quote price
    for n in ctx["needs"]:
        for p in [n["product_id"]] + n["alts"]:
            if allow_purchases and p in ctx["quotes"]:
                purchasable[(n["id"], p)] = ctx["quotes"][p]
    buy = {}
    for key, price in purchasable.items():
        buy[key] = model.NewIntVar(0, needs[key[0]]["qty"], f"b{key[0]}_{key[1]}")

    cov = {}
    for n in ctx["needs"]:
        terms = [qty[i] for i, c in enumerate(cycles) if any(e.need_id == n["id"] for e in c.legs)]
        terms += [buy[k] for k in buy if k[0] == n["id"]]
        v = model.NewIntVar(0, n["qty"], f"cov{n['id']}")
        if terms:
            model.Add(v <= sum(terms))   # maximised; overshoot is never useful
        else:
            model.Add(v == 0)
        cov[n["id"]] = v

    # per-shop cash: balancing payments + purchases + transport share ≤ confirmed cash limit
    for s, shop in ctx["shops"].items():
        cash_parts = []
        for i, c in enumerate(cycles):
            if s in _shops_in(c):
                bal = _balancing_per_pack(c, s)
                tr = _transport_paise(c) // len(_shops_in(c))   # integer split, same as receipts
                cash_parts.append((qty[i], bal + tr))
        for k, price in purchasable.items():
            if needs[k[0]]["shop_id"] == s:
                cash_parts.append((buy[k], price))
        if cash_parts:
            model.Add(sum(coef * v for v, coef in cash_parts) <= shop["cash_limit_paise"])

    # at most one selected exchange cycle per shop in a planning run
    for s in ctx["shops"]:
        involved = [sel[i] for i, c in enumerate(cycles) if s in _shops_in(c)]
        if involved:
            model.Add(sum(involved) <= 1)

    objective_vars, objective_coeffs = [], []
    for n in ctx["needs"]:
        objective_vars.append(cov[n["id"]])
        objective_coeffs.append(COVERAGE_WEIGHT * URGENCY_WEIGHTS.get(n["urgency"], 1))
    for i, c in enumerate(cycles):
        slow_legs = sum(1 for e in c.legs if e.slow)   # bonus per redeployed slow pack
        if slow_legs:
            objective_vars.append(qty[i])
            objective_coeffs.append(SLOW_REDEPLOY_BONUS_PAISE * slow_legs)
    for i, c in enumerate(cycles):
        objective_vars.append(qty[i])
        objective_coeffs.append(-_transport_paise(c))
    for k, price in purchasable.items():
        objective_vars.append(buy[k])
        objective_coeffs.append(-price)
    model.Maximize(cp_model.LinearExpr.WeightedSum(objective_vars, objective_coeffs))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.2, time_limit_ms / 1000)
    solver.parameters.num_workers = 8
    t0 = time.perf_counter()
    status = solver.Solve(model)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    status_name = solver.StatusName(status)   # OPTIMAL | FEASIBLE | INFEASIBLE | UNKNOWN
    feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    out = {"status": status_name, "time_ms": elapsed_ms, "proven_optimal": status_name == "OPTIMAL",
           "objective": int(round(solver.ObjectiveValue())) if feasible else None}
    if collect_solution and feasible:
        out["cycle_qty"] = [int(solver.Value(q)) for q in qty]
        out["buy"] = {k: int(solver.Value(v)) for k, v in buy.items() if solver.Value(v) > 0}
    return out


def plan(ctx: dict, cycles: list, params: dict) -> dict:
    """Full planning pass: main solve + 'why not' comparisons + proposal assembly."""
    time_limit = params.get("time_limit_ms", DEFAULT_TIME_LIMIT_MS)
    allow_purchases = params.get("include_purchases", True)
    main = solve_model(cycles, ctx, time_limit, allow_purchases=allow_purchases)
    log = [f"enumerated {len(cycles)} candidate cycles",
           f"main solve: {main['status']} in {main['time_ms']}ms"]

    proposal = {"participants": [], "cycles": [], "purchases": [], "coverage": [],
                "costs": {}, "assumptions": [], "solver": {}, "why_not": None}
    if main["objective"] is None:
        proposal["solver"] = {"status": main["status"], "objective": None,
                              "time_ms": main["time_ms"], "proven_optimal": False}
        proposal["assumptions"] = ["No plan was proven within the time limit; "
                                   "this is not proof of infeasibility. Speak to the operator or retry."]
        proposal["log"] = log
        return proposal

    names = ctx["names"]
    selected = [(cycles[i], q) for i, q in enumerate(main.get("cycle_qty", [])) if q > 0]
    buys = main.get("buy", {})

    participants, balancing, cash_out = set(), {}, {}
    transport_total = slow_packs = goods_value = purchase_cash = 0
    cov_rows = {n["id"]: {"shop_id": n["shop_id"], "need_id": n["id"], "product_id": n["product_id"],
                          "product_name": names[n["product_id"]]["name"],
                          "emoji": names[n["product_id"]]["emoji"],
                          "qty_needed": n["qty"], "qty_covered": 0, "source": "none",
                          "urgency": n["urgency"]}
                for n in ctx["needs"]}

    for ci, (c, q) in enumerate(selected):
        shops_in = sorted(_shops_in(c))
        participants.update(shops_in)
        tp = _transport_paise(c)
        transport_total += tp * q
        legs = []
        for e in c.legs:
            goods_value += e.unit_value_paise * q
            if e.slow:
                slow_packs += q
            prod = names[e.product_id]
            legs.append({"from_shop": e.giver, "to_shop": e.receiver, "product_id": e.product_id,
                         "product_name": prod["name"], "emoji": prod["emoji"], "qty": q,
                         "unit": prod["unit"], "unit_value_paise": e.unit_value_paise,
                         "value_paise": e.unit_value_paise * q,
                         "min_shelf_days": e.min_shelf_days, "slow": e.slow})
        bal_by_shop = {s: _balancing_per_pack(c, s) * q for s in shops_in}
        for s, v in bal_by_shop.items():
            balancing[s] = balancing.get(s, 0) + v
            cash_out[s] = cash_out.get(s, 0) + max(0, v) + tp * q // len(shops_in)
        proposal["cycles"].append({
            "id": f"c{ci + 1}", "shop_path": c.shop_path, "legs": legs,
            "balancing_paise_by_shop": {str(s): v for s, v in bal_by_shop.items()},
            "transport_paise": tp, "transport_per_shop_paise": tp // len(shops_in),
            "slow_packs_redeployed": sum(q for e in c.legs if e.slow)})

    purchases = []
    for (need_id, pid), q in sorted(buys.items()):
        n = next(x for x in ctx["needs"] if x["id"] == need_id)
        price = ctx["quotes"][pid]
        purchases.append({"shop_id": n["shop_id"], "product_id": pid,
                          "product_name": names[pid]["name"], "emoji": names[pid]["emoji"],
                          "qty": q, "unit_price_paise": price, "total_paise": price * q})
        purchase_cash += price * q
        participants.add(n["shop_id"])
        cash_out[n["shop_id"]] = cash_out.get(n["shop_id"], 0) + price * q
        cov_rows[need_id]["qty_covered"] += q
        cov_rows[need_id]["source"] = "purchase"

    for c, q in selected:
        for e in c.legs:
            row = cov_rows.get(e.need_id)
            if row:
                row["qty_covered"] += q
                row["source"] = "exchange"   # an accepted alternative still covers the need

    proposal.update({
        "participants": sorted(participants),
        "purchases": purchases,
        "coverage": list(cov_rows.values()),
        "costs": {
            "goods_value_exchanged_paise": goods_value,
            "balancing_net_by_shop": {str(s): balancing.get(s, 0) for s in sorted(participants)},
            "purchases_paise": purchase_cash,
            "transport_paise": transport_total,
            "transaction_fee_paise": 0,
            "cash_out_by_shop": {str(s): cash_out.get(s, 0) for s in sorted(participants)},
        },
        "solver": {"status": main["status"], "objective": main["objective"],
                   "time_ms": main["time_ms"], "proven_optimal": main["proven_optimal"]},
        "assumptions": _assumptions(),
        "why_not": _why_not(ctx, cycles, params),
        "slow_packs_redeployed": slow_packs,
        "log": log + [f"selected {len(selected)} cycles, {len(purchases)} purchase lines"],
    })
    return proposal


def _assumptions() -> list:
    return [
        f"Transport charged at ₹{TRANSPORT_RATE_PAISE_PER_PACK_KM // 100}/pack-km plus ₹{TRANSPORT_BASE_PAISE // 100} call-out, split evenly between cycle participants.",
        "Unit values come from each giver's confirmed purchase cost; balancing payments settle value differences inside this plan only and are never netted across plans.",
        "Purchases use the lowest current supplier quote; a missing quote makes that line unpriceable and it is shown as an assumption, never as zero.",
        "Exchanged goods remain a taxable supply under the shops' own professional process; exported records support review, they do not decide GST treatment.",
        "Balancing payments are modelled in a labelled sandbox; no live settlement, atomic swap or trade-credit arrangement is implied.",
    ]


def _why_not(ctx: dict, cycles: list, params: dict) -> dict:
    """Restricted re-solves so every plan can say why the obvious alternatives lost."""
    t = max(1000, params.get("time_limit_ms", DEFAULT_TIME_LIMIT_MS) // 3)
    out = {"all_purchase": _coverage_summary(ctx, [], solve_model([], ctx, t))}
    two = [c for c in cycles if len(c.legs) == 2]
    out["pairwise_only"] = _coverage_summary(ctx, two, solve_model(two, ctx, t)) if two else \
        {"coverage_pct": 0, "note": "no feasible bilateral swap exists in this cluster"}
    slow = [c for c in cycles if any(e.slow for e in c.legs)]
    out["expiry_move_only"] = _coverage_summary(ctx, slow, solve_model(slow, ctx, t, allow_purchases=False)) \
        if slow else {"coverage_pct": 0, "cash_paise": 0,
                      "note": "no near-expiry slow stock matches any confirmed need"}
    out["expiry_move_only"]["note"] = out["expiry_move_only"].get("note",
        "pure redeployment of slow/near-expiry stock, no purchases allowed")
    return out


def _result_cash(ctx: dict, cycles: list, result: dict) -> int:
    cash = sum(ctx["quotes"][pid] * q for (nid, pid), q in result.get("buy", {}).items())
    for i, c in enumerate(cycles):
        q = result.get("cycle_qty", [0] * len(cycles))[i]
        if q:
            cash += _transport_paise(c) * q
    return cash


def _coverage_summary(ctx: dict, cycles: list, result: dict) -> dict:
    total_needed = sum(n["qty"] for n in ctx["needs"])
    if result.get("objective") is None:
        return {"coverage_pct": 0, "cash_paise": 0, "note": f"solver status: {result.get('status')}"}
    cov = {n["id"]: 0 for n in ctx["needs"]}
    for i, c in enumerate(cycles):
        q = result["cycle_qty"][i]
        if q:
            for e in c.legs:
                if e.need_id in cov:
                    cov[e.need_id] += q
    for (need_id, _pid), q in result.get("buy", {}).items():
        cov[need_id] += q
    qty_by_need = {n["id"]: n["qty"] for n in ctx["needs"]}
    covered = sum(min(v, qty_by_need[k]) for k, v in cov.items())
    return {"coverage_pct": round(100 * covered / total_needed, 1) if total_needed else 0.0,
            "cash_paise": _result_cash(ctx, cycles, result)}
