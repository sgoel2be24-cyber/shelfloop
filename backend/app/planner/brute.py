"""Independent exhaustive reference for bounded, small planning instances."""
from itertools import product

from ..config import URGENCY_WEIGHTS
from .graph import available_qty
from .solve import _purchase_options, _shops_in, cycle_cash_out


def brute_force(cycles, ctx, max_packs_per_need: int = 6, allow_purchases=True):
    needs = {n["id"]: n for n in ctx["needs"]}
    if any(n["qty"] > max_packs_per_need for n in needs.values()):
        raise ValueError("exhaustive reference only accepts small need quantities")
    if len(cycles) > 12:
        raise ValueError("exhaustive reference only accepts at most 12 cycle candidates")
    spaces = []
    for need in ctx["needs"]:
        choices = [(need["id"], None, 0, 0)]
        for pid, price, minimum in _purchase_options(ctx, need, allow_purchases):
            choices.extend((need["id"], pid, qty, price)
                           for qty in range(minimum, need["qty"] + 1))
        spaces.append(choices)

    best, best_vector = None, None
    for quantities in product(*(range(c.max_qty + 1) for c in cycles)):
        used_shops, cycle_coverage, cycle_cash, valid = set(), {}, {}, True
        slow = burden = 0
        for cycle, qty in zip(cycles, quantities):
            if not qty:
                continue
            shops = _shops_in(cycle)
            if used_shops & shops:
                valid = False
                break
            used_shops.update(shops)
            for leg in cycle.legs:
                if qty > available_qty(ctx, leg.giver, leg.product_id, leg.min_shelf_days):
                    valid = False
                cycle_coverage[leg.need_id] = cycle_coverage.get(leg.need_id, 0) + qty
                slow += qty if leg.slow else 0
            for shop, outlay in cycle_cash_out(cycle, qty).items():
                cycle_cash[shop] = cycle_cash.get(shop, 0) + outlay
            burden += int(round(sum(e.dist_km for e in cycle.legs) * 1000)) * qty
        if not valid:
            continue

        for buys in product(*spaces):
            cash, coverage = dict(cycle_cash), dict(cycle_coverage)
            for nid, pid, qty, price in buys:
                coverage[nid] = coverage.get(nid, 0) + qty
                shop = needs[nid]["shop_id"]
                cash[shop] = cash.get(shop, 0) + qty * price
            if any(v > ctx["shops"][s]["cash_limit_paise"] for s, v in cash.items()):
                continue
            if any(v > needs[nid]["qty"] for nid, v in coverage.items()):
                continue
            weighted = sum(coverage.get(nid, 0) * URGENCY_WEIGHTS.get(n["urgency"], 1)
                           for nid, n in needs.items())
            vector = (weighted, -sum(cash.values()), slow, -burden)
            if best_vector is None or vector > best_vector:
                best_vector = vector
                best = {"objective": weighted, "objective_vector": list(vector),
                        "cycles": [(c, q) for c, q in zip(cycles, quantities) if q],
                        "buy": [(nid, pid, q) for nid, pid, q, price in buys if q]}
    return best
