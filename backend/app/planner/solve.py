"""CP-SAT planner. Exact lexicographic priorities, integer paise throughout:
1. maximise coverage of owner-confirmed needs (urgent counts double)
2. minimise additional cash: purchases + known transaction/transport costs
3. prefer redeploying explicitly marked slow stock
4. minimise transport burden
Solver status is reported verbatim: a timeout is FEASIBLE/UNKNOWN, never 'infeasible'."""
import time

from ortools.sat.python import cp_model

from ..config import (DEFAULT_TIME_LIMIT_MS,
                      TRANSPORT_BASE_PAISE, TRANSPORT_RATE_PAISE_PER_PACK_KM, URGENCY_WEIGHTS)
from .graph import Cycle


def _balancing_per_pack(cycle: Cycle, shop_id: int) -> int:
    """value received − value given, per pack, for one participant of one cycle."""
    vin = sum(e.unit_value_paise for e in cycle.legs if e.receiver == shop_id)
    vout = sum(e.unit_value_paise for e in cycle.legs if e.giver == shop_id)
    return vin - vout


def _transport_paise(cycle: Cycle) -> int:
    """Compatibility helper: total charge for a one-pack cycle."""
    return cycle_transport_paise(cycle, 1)


def _shops_in(cycle: Cycle) -> set:
    return {e.giver for e in cycle.legs} | {e.receiver for e in cycle.legs}


def _variable_transport(cycle: Cycle) -> int:
    return int(round(TRANSPORT_RATE_PAISE_PER_PACK_KM * sum(e.dist_km for e in cycle.legs)))


def cycle_transport_paise(cycle: Cycle, qty: int) -> int:
    """One call-out per selected cycle, not one per pack."""
    return TRANSPORT_BASE_PAISE + _variable_transport(cycle) * qty if qty > 0 else 0


def cycle_transport_shares(cycle: Cycle, qty: int) -> dict:
    shops = sorted(_shops_in(cycle))
    if qty <= 0:
        return {s: 0 for s in shops}
    base, base_remainder = divmod(TRANSPORT_BASE_PAISE, len(shops))
    per_pack, pack_remainder = divmod(_variable_transport(cycle), len(shops))
    return {s: base + int(i < base_remainder) + qty * (per_pack + int(i < pack_remainder))
            for i, s in enumerate(shops)}


def cycle_cash_out(cycle: Cycle, qty: int) -> dict:
    """Conservative cash obligations: incoming balancing money is not available funds."""
    return {s: max(0, _balancing_per_pack(cycle, s) * qty) + share
            for s, share in cycle_transport_shares(cycle, qty).items()}


def _purchase_options(ctx, need, allow_purchases=True):
    if not allow_purchases:
        return []
    options = []
    for pid in dict.fromkeys([need["product_id"]] + need.get("alts", [])):
        for quote in ctx.get("quote_options", {}).get(pid, []):
            if 0 <= quote["price_paise"] and 1 <= quote["min_order_packs"] <= need["qty"]:
                options.append((pid, quote["price_paise"], quote["min_order_packs"]))
        if pid not in ctx.get("quote_options", {}) and pid in ctx["quotes"]:
            options.append((pid, ctx["quotes"][pid], 1))
    return sorted(set(options))


def objective_vector(ctx, cycles, quantities, buys, prices=None):
    covered = {n["id"]: 0 for n in ctx["needs"]}
    cash = slow = burden = 0
    for cycle, qty in zip(cycles, quantities):
        if qty <= 0:
            continue
        cash += sum(cycle_cash_out(cycle, qty).values())
        burden += int(round(sum(e.dist_km for e in cycle.legs) * 1000)) * qty
        for leg in cycle.legs:
            covered[leg.need_id] += qty
            slow += qty if leg.slow else 0
    for key, qty in buys.items():
        covered[key[0]] += qty
        cash += (prices or {}).get(key, ctx["quotes"][key[1]]) * qty
    weighted = sum(covered[n["id"]] * URGENCY_WEIGHTS.get(n["urgency"], 1) for n in ctx["needs"])
    return (weighted, -cash, slow, -burden)


def solve_model(cycles: list, ctx: dict, time_limit_ms: int, collect_solution: bool = True,
                allow_purchases: bool = True) -> dict:
    """Fix coverage first, then optimise bounded lower priorities in one pass.

    The shared deadline includes model construction and all objective stages. An
    interrupted lower-priority pass preserves its last valid incumbent as FEASIBLE.
    `objective` remains a numeric primary score for existing API consumers; the
    complete ordering is exposed as `objective_vector`.
    """
    t0 = time.perf_counter()
    deadline = t0 + max(0, time_limit_ms) / 1000
    model = cp_model.CpModel()
    qty = [model.NewIntVar(0, c.max_qty, f"q{i}") for i, c in enumerate(cycles)]
    sel = [model.NewBoolVar(f"s{i}") for i, c in enumerate(cycles)]
    for i, c in enumerate(cycles):
        model.Add(qty[i] <= c.max_qty * sel[i])
        model.Add(sel[i] <= qty[i])

    needs = {n["id"]: n for n in ctx["needs"]}
    options = {}  # (need_id, option_index) -> product, price, minimum quantity
    for n in ctx["needs"]:
        for j, option in enumerate(_purchase_options(ctx, n, allow_purchases)):
            options[(n["id"], j)] = option
    buy = {}
    buy_selected = {}
    for key, (pid, price, minimum) in options.items():
        buy[key] = model.NewIntVar(0, needs[key[0]]["qty"], f"b{key[0]}_{key[1]}")
        buy_selected[key] = model.NewBoolVar(f"bs{key[0]}_{key[1]}")
        model.Add(buy[key] <= needs[key[0]]["qty"] * buy_selected[key])
        model.Add(buy[key] >= minimum * buy_selected[key])
    for n in ctx["needs"]:
        chosen = [buy_selected[k] for k in options if k[0] == n["id"]]
        if chosen:
            model.Add(sum(chosen) <= 1)

    cov = {}
    for n in ctx["needs"]:
        terms = [qty[i] for i, c in enumerate(cycles) if any(e.need_id == n["id"] for e in c.legs)]
        terms += [buy[k] for k in buy if k[0] == n["id"]]
        v = model.NewIntVar(0, n["qty"], f"cov{n['id']}")
        if terms:
            model.Add(v == sum(terms))  # never overdeliver an owner-confirmed need
        else:
            model.Add(v == 0)
        cov[n["id"]] = v

    # One shared accounting policy drives budgets, receipts, exhaustive checks
    # and benchmarks. Every transport paise is assigned to a participant.
    transport = []
    cycle_shop_cost = {}
    for i, c in enumerate(cycles):
        shops = sorted(_shops_in(c))
        tp = TRANSPORT_BASE_PAISE * sel[i] + _variable_transport(c) * qty[i]
        transport.append(tp)
        base_shares = cycle_transport_shares(c, 1)
        two_shares = cycle_transport_shares(c, 2)
        for rank, s in enumerate(shops):
            # Apportion base once and each pack-distance charge deterministically.
            # Linear expressions avoid thousands of integer divisions in dense graphs.
            per_pack = two_shares[s] - base_shares[s]
            share = (base_shares[s] - per_pack) * sel[i] + per_pack * qty[i]
            cycle_shop_cost[i, s] = max(0, _balancing_per_pack(c, s)) * qty[i] + share

    cash_terms = []
    for s, shop in ctx["shops"].items():
        cash_parts = [v for (i, sid), v in cycle_shop_cost.items() if sid == s]
        for k, (pid, price, minimum) in options.items():
            if needs[k[0]]["shop_id"] == s:
                cash_parts.append(buy[k] * price)
        if cash_parts:
            model.Add(sum(cash_parts) <= max(0, shop["cash_limit_paise"]))
            cash_terms.extend(cash_parts)

    # at most one selected exchange cycle per shop in a planning run
    for s in ctx["shops"]:
        involved = [sel[i] for i, c in enumerate(cycles) if s in _shops_in(c)]
        if involved:
            model.Add(sum(involved) <= 1)

    stages = [
        (sum(cov[n["id"]] * URGENCY_WEIGHTS.get(n["urgency"], 1) for n in ctx["needs"]), True),
        (sum(cash_terms), False),
        (sum(qty[i] * sum(int(e.slow) for e in c.legs) for i, c in enumerate(cycles)), True),
        (sum(qty[i] * int(round(sum(e.dist_km for e in c.legs) * 1000))
             for i, c in enumerate(cycles)), False),
    ]
    # Bound the four aggregates before encoding their priorities. Unlike fixed
    # magic weights, each multiplier exceeds the *entire* lower-priority range.
    # This gives a single exact lexicographic solve for ordinary shop-sized
    # inputs, avoiding four expensive full searches. Huge inputs retain the
    # sequential path so the integer objective cannot overflow CP-SAT's int64.
    coverage_bound = sum(n["qty"] * URGENCY_WEIGHTS.get(n["urgency"], 1) for n in ctx["needs"])
    cash_bound = sum(max(0, s["cash_limit_paise"]) for s in ctx["shops"].values())
    slow_bound = sum(n["qty"] for n in ctx["needs"])
    max_metres = max((int(e.dist_km * 1000) + 2 for c in cycles for e in c.legs), default=0)
    burden_bound = max_metres * slow_bound
    aggregate = []
    for i, ((expr, maximise), bound) in enumerate(zip(stages, (
            coverage_bound, cash_bound, slow_bound, burden_bound))):
        value = model.NewIntVar(0, bound, f"objective_stage{i}")
        model.Add(value == expr)
        aggregate.append(value)
    slow_weight = burden_bound + 1
    cash_weight = (slow_bound + 1) * slow_weight
    encoded_bound = cash_bound * cash_weight + slow_bound * slow_weight + burden_bound
    bounded_encoding = encoded_bound < 2**62
    stage_credits = [1, 1, 1, 1]
    if bounded_encoding:
        stages = [(aggregate[0], True),
                  (aggregate[1] * cash_weight - aggregate[2] * slow_weight + aggregate[3], False)]
        stage_credits = [1, 3]

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 4 if len(cycles) >= 50 else 1
    solver.parameters.random_seed = 0
    incumbent = None
    status_name = "UNKNOWN"
    completed_stages = 0
    for (expr, maximise), credit in zip(stages, stage_credits):
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            status_name = "FEASIBLE" if incumbent is not None else "UNKNOWN"
            break
        model.Maximize(expr) if maximise else model.Minimize(expr)
        solver.parameters.max_time_in_seconds = remaining
        status = solver.Solve(model)
        stage_status = solver.StatusName(status)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            status_name = "FEASIBLE" if incumbent is not None else stage_status
            break
        picked, prices = {}, {}
        for k, v in buy.items():
            q = int(solver.Value(v))
            if q:
                key = (k[0], options[k][0])
                picked[key], prices[key] = q, options[k][1]
        quantities = [int(solver.Value(q)) for q in qty]
        incumbent = (quantities, picked, prices)
        status_name = stage_status
        if status != cp_model.OPTIMAL:
            break
        completed_stages += credit
        model.Add(expr == int(solver.Value(expr)))
        model.ClearHints()
        for variable in qty + sel + list(buy.values()) + list(buy_selected.values()) + list(cov.values()) + aggregate:
            model.AddHint(variable, int(solver.Value(variable)))
    feasible = incumbent is not None
    vector = objective_vector(ctx, cycles, *incumbent) if feasible else None
    out = {"status": status_name, "time_ms": int((time.perf_counter() - t0) * 1000),
           "proven_optimal": feasible and completed_stages == 4,
           "objective": vector[0] if feasible else None,
           "objective_vector": list(vector) if feasible else None,
           "objective_stages_completed": completed_stages,
           "objective_encoding": "bounded_lexicographic" if bounded_encoding else "sequential"}
    if feasible and not out["proven_optimal"]:
        out["status"] = "FEASIBLE"
    if collect_solution and feasible:
        out["cycle_qty"], out["buy"], out["buy_prices"] = incumbent
    return out


def plan(ctx: dict, cycles: list, params: dict) -> dict:
    """Full planning pass: main solve + 'why not' comparisons + proposal assembly."""
    started = time.perf_counter()
    time_limit = params.get("time_limit_ms", DEFAULT_TIME_LIMIT_MS)
    deadline = started + time_limit / 1000
    allow_purchases = params.get("include_purchases", True)
    main = solve_model(cycles, ctx, time_limit, allow_purchases=allow_purchases)
    log = [f"enumerated {len(cycles)} candidate cycles",
           f"main solve: {main['status']} in {main['time_ms']}ms"]

    proposal = {"participants": [], "cycles": [], "purchases": [], "coverage": [],
                "costs": {}, "assumptions": [], "solver": {}, "why_not": None}
    if main["objective"] is None:
        proposal["solver"] = {"status": main["status"], "objective": None,
                              "time_ms": main["time_ms"], "proven_optimal": False}
        proposal["assumptions"] = [
            "The candidate model is infeasible." if main["status"] == "INFEASIBLE" else
            "No valid plan was found within the time limit; this is not proof of infeasibility. Retry or ask the operator."]
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
        tp = cycle_transport_paise(c, q)
        shares = cycle_transport_shares(c, q)
        transport_total += tp
        legs = []
        for e in c.legs:
            goods_value += e.unit_value_paise * q
            if e.slow:
                slow_packs += q
            prod = names[e.product_id]
            legs.append({"from_shop": e.giver, "to_shop": e.receiver, "need_id": e.need_id,
                         "product_id": e.product_id,
                         "product_name": prod["name"], "emoji": prod["emoji"], "qty": q,
                         "unit": prod["unit"], "unit_value_paise": e.unit_value_paise,
                         "value_paise": e.unit_value_paise * q,
                         "min_shelf_days": e.min_shelf_days, "slow": e.slow})
        bal_by_shop = {s: _balancing_per_pack(c, s) * q for s in shops_in}
        for s, v in bal_by_shop.items():
            balancing[s] = balancing.get(s, 0) + v
            cash_out[s] = cash_out.get(s, 0) + max(0, v) + shares[s]
        proposal["cycles"].append({
            "id": f"c{ci + 1}", "shop_path": c.shop_path, "legs": legs,
            "balancing_paise_by_shop": {str(s): v for s, v in bal_by_shop.items()},
            "transport_paise": tp, "transport_per_shop_paise": tp // len(shops_in),
            "transport_by_shop_paise": {str(s): share for s, share in shares.items()},
            "slow_packs_redeployed": sum(q for e in c.legs if e.slow)})

    purchases = []
    for (need_id, pid), q in sorted(buys.items()):
        n = next(x for x in ctx["needs"] if x["id"] == need_id)
        price = main.get("buy_prices", {}).get((need_id, pid), ctx["quotes"][pid])
        purchases.append({"shop_id": n["shop_id"], "need_id": need_id, "product_id": pid,
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
                row["source"] = "mixed" if row["source"] == "purchase" else "exchange"

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
            "gross_cash_out_paise": sum(cash_out.values()),
            "external_cash_paise": purchase_cash + transport_total,
            "balancing_cash_paise": sum(max(0, v) for v in balancing.values()),
        },
        "solver": {"status": main["status"], "objective": main["objective"],
                   "time_ms": main["time_ms"], "proven_optimal": main["proven_optimal"],
                   "objective_vector": main["objective_vector"],
                   "objective_stages_completed": main["objective_stages_completed"],
                   "candidate_search_complete": not ctx.get("candidate_truncated", False)},
        "assumptions": _assumptions(),
        "why_not": _why_not(ctx, cycles, params, deadline),
        "slow_packs_redeployed": slow_packs,
        "log": log + [f"selected {len(selected)} cycles, {len(purchases)} purchase lines"],
    })
    proposal["solver"]["total_time_ms"] = int((time.perf_counter() - started) * 1000)
    if ctx.get("candidate_truncated"):
        proposal["assumptions"].append("Candidate enumeration reached its safety limit; optimality only describes the retained candidates.")
    return proposal


def _assumptions() -> list:
    return [
        f"Transport charged at ₹{TRANSPORT_RATE_PAISE_PER_PACK_KM // 100}/pack-km plus one ₹{TRANSPORT_BASE_PAISE // 100} call-out per cycle; base and each pack charge are split in integer paise, with remainders assigned by ascending shop ID.",
        "Unit values come from eligible lots' confirmed purchase costs. Incoming balancing receipts never finance purchases; positive balancing payments are included in each owner's cash obligation.",
        "Purchases use the lowest current supplier quote; a missing quote makes that line unpriceable and it is shown as an assumption, never as zero.",
        "Exchanged goods remain a taxable supply under the shops' own professional process; exported records support review, they do not decide GST treatment.",
        "Balancing payments are modelled in a labelled sandbox; no live settlement, atomic swap or trade-credit arrangement is implied.",
    ]


def _why_not(ctx: dict, cycles: list, params: dict, deadline: float) -> dict:
    """Restricted re-solves so every plan can say why the obvious alternatives lost."""
    two = [c for c in cycles if len(c.legs) == 2]
    slow = [c for c in cycles if any(e.slow for e in c.legs)]
    out = {}
    for idx, (name, subset, buys) in enumerate((
            ("all_purchase", [], True), ("pairwise_only", two, True),
            ("expiry_move_only", slow, False))):
        remaining = max(0, int((deadline - time.perf_counter()) * 1000 / (3 - idx)))
        if remaining <= 0:
            out[name] = {"coverage_pct": 0, "cash_paise": 0, "status": "NOT_RUN",
                         "note": "comparison skipped because the shared planning deadline was reached"}
        else:
            out[name] = _coverage_summary(ctx, subset, solve_model(subset, ctx, remaining, allow_purchases=buys))
    out["expiry_move_only"]["note"] = out["expiry_move_only"].get("note",
        "pure redeployment of slow/near-expiry stock, no purchases allowed")
    return out


def _result_cash(ctx: dict, cycles: list, result: dict) -> int:
    cash = sum(result.get("buy_prices", {}).get((nid, pid), ctx["quotes"][pid]) * q
               for (nid, pid), q in result.get("buy", {}).items())
    for i, c in enumerate(cycles):
        q = result.get("cycle_qty", [0] * len(cycles))[i]
        if q:
            cash += sum(cycle_cash_out(c, q).values())
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
            "cash_paise": _result_cash(ctx, cycles, result), "status": result["status"],
            "proven_optimal": result["proven_optimal"]}
