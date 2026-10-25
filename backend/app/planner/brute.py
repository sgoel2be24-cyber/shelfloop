"""Exhaustive reference solver for small cases. Same objective and constraints as
solve.py, evaluated by brute force. Used by tests to check CP-SAT optimality claims."""
from itertools import product

from .graph import available_qty
from .solve import _balancing_per_pack, _shops_in, _transport_paise


def brute_force(cycles, ctx, max_packs_per_need: int = 6):
    needs = {n["id"]: n for n in ctx["needs"]}
    buy_options = {}
    for n in ctx["needs"]:
        for p in [n["product_id"]] + n["alts"]:
            if p in ctx["quotes"]:
                buy_options.setdefault(n["id"], []).append((p, ctx["quotes"][p]))

    best = None
    n = len(cycles)
    buy_spaces = [[(nid, p, q) for (p, _price) in opts
                   for q in range(0, min(needs[nid]["qty"], max_packs_per_need) + 1)]
                  for nid, opts in buy_options.items()]

    for mask in range(1 << n):
        chosen = [cycles[i] for i in range(n) if mask >> i & 1]
        for combo in product(*[range(1, c.max_qty + 1) for c in chosen]) if chosen else [()]:
            supply, shop_cycles = {}, {}
            ok = True
            for c, q in zip(chosen, combo):
                for s in _shops_in(c):
                    shop_cycles[s] = shop_cycles.get(s, 0) + 1
                    if shop_cycles[s] > 1:
                        ok = False
                for e in c.legs:
                    supply[(e.giver, e.product_id, e.min_shelf_days)] = \
                        supply.get((e.giver, e.product_id, e.min_shelf_days), 0) + q
            if not ok:
                continue
            for (g, p, ms), q in supply.items():
                if q > available_qty(ctx, g, p, ms):
                    ok = False
                    break
            if not ok:
                continue
            for combo_buys in product(*buy_spaces) if buy_spaces else [()]:
                cash = {}
                valid = True
                cov = {nid: 0 for nid in needs}
                for c, q in zip(chosen, combo):
                    for s in _shops_in(c):
                        cash[s] = cash.get(s, 0) + _balancing_per_pack(c, s) * q \
                            + _transport_paise(c) * q // len(_shops_in(c))
                    for e in c.legs:
                        cov[e.need_id] += q
                for (nid, pid, q) in combo_buys:
                    shop = needs[nid]["shop_id"]
                    cash[shop] = cash.get(shop, 0) + q * ctx["quotes"][pid]
                    cov[nid] += q
                for s, v in cash.items():
                    if v > ctx["shops"][s]["cash_limit_paise"]:
                        valid = False
                        break
                if not valid:
                    continue
                for nid, got in cov.items():
                    if got > needs[nid]["qty"]:
                        valid = False
                        break
                if not valid:
                    continue
                obj = objective(ctx, needs, chosen, combo, combo_buys, buy_options)
                if best is None or obj > best["objective"]:
                    best = {"objective": obj, "cycles": [(c, q) for c, q in zip(chosen, combo)],
                            "buy": [(nid, pid, q) for nid, pid, q in combo_buys if q]}
    return best


def pid_price(ctx, need_id, product_id):
    return ctx["quotes"][product_id]


def objective(ctx, needs, chosen, combo, combo_buys, buy_options):
    from ..config import COVERAGE_WEIGHT, SLOW_REDEPLOY_BONUS_PAISE, URGENCY_WEIGHTS
    cov = {nid: 0 for nid in needs}
    cash = 0
    slow = 0
    for c, q in zip(chosen, combo):
        for e in c.legs:
            cov[e.need_id] += q
            if e.slow:
                slow += q
        cash += _transport_paise(c) * q
    for (nid, pid, q) in combo_buys:
        cov[nid] += q
        cash += ctx["quotes"][pid] * q
    obj = sum(COVERAGE_WEIGHT * URGENCY_WEIGHTS.get(needs[nid]["urgency"], 1) * min(v, needs[nid]["qty"])
              for nid, v in cov.items())
    obj += SLOW_REDEPLOY_BONUS_PAISE * slow - cash
    return obj
