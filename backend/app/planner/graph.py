"""Builds the planning world: availability, confirmed needs, candidate give/receive
edges and feasible 2-/3-shop cycles. Pure data; no solving here."""
import math
from itertools import combinations, product
from dataclasses import dataclass, field
from datetime import date

from .. import db
from ..config import DEFAULT_MIN_SHELF_DAYS, DEFAULT_RADIUS_KM, MAX_CYCLES, MAX_PRODUCTS_PER_PAIR


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def days_to_expiry(expiry_iso: str | None, today: date) -> int | None:
    try:
        return (date.fromisoformat(expiry_iso) - today).days if expiry_iso else None
    except (ValueError, TypeError):
        return None


@dataclass
class Edge:
    giver: int
    receiver: int
    need_id: int
    product_id: int
    max_qty: int
    unit_value_paise: int
    dist_km: float
    slow: bool
    min_shelf_days: int


@dataclass
class Cycle:
    legs: tuple                    # tuple[Edge, ...]; legs[i] goes legs[i].giver -> legs[i].receiver
    max_qty: int
    key: tuple = field(default="", compare=False)

    @property
    def shop_path(self):
        return [leg.giver for leg in self.legs]


def available_qty(ctx: dict, giver: int, product_id: int, min_shelf_days: int) -> int:
    return sum(_free_qty(lot) for lot in eligible_lots(
        ctx["lots"], giver, product_id, min_shelf_days, ctx["today"]))


def _free_qty(lot):
    return max(0, lot["qty"] - lot["retained_floor"] - lot.get("reserved_qty", 0))


def build_context(conn, params: dict) -> dict:
    """Snapshot of confirmed state used by every planner variant."""
    today = date.today()
    min_shelf_default = params.get("min_shelf_days", DEFAULT_MIN_SHELF_DAYS)
    radius = params.get("radius_km", DEFAULT_RADIUS_KM)

    shops = {}
    selected_shops = set(params.get("shop_ids") or [])
    for r in conn.execute("SELECT * FROM shops"):
        if selected_shops and r["id"] not in selected_shops:
            continue
        shops[r["id"]] = dict(r)

    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "cash_reservations" in tables:
        for row in conn.execute("SELECT shop_id, SUM(amount_paise) held FROM cash_reservations "
                                "WHERE (status='active' AND expires_at > ?) OR status='pending_operator' "
                                "GROUP BY shop_id", (db.now_iso(),)):
            shop = shops.get(row["shop_id"])
            if shop:
                shop["cash_limit_paise"] = max(0, shop["cash_limit_paise"] - row["held"])

    lots = {}   # (shop, product) -> [lot dicts]
    held = {r["lot_id"]: r["held"] for r in conn.execute(
        "SELECT lot_id, SUM(qty) held FROM reservations WHERE status='active' AND expires_at > ? "
        "GROUP BY lot_id", (db.now_iso(),))}
    for r in conn.execute("SELECT * FROM stock_lots"):
        if r["shop_id"] not in shops:
            continue
        lot = dict(r)
        lot["reserved_qty"] = held.get(r["id"], 0)
        lots.setdefault((r["shop_id"], r["product_id"]), []).append(lot)

    needs = []
    for r in conn.execute("SELECT * FROM needs WHERE status='open'"):
        if r["shop_id"] not in shops:
            continue
        n = dict(r)
        n["alts"] = [int(x) for x in db.jload(r["alt_product_ids"], [])]
        n["min_shelf_days"] = max(r["min_shelf_days"] or 0, min_shelf_default)
        needs.append(n)
    needs = [n for n in needs if not shops[n["shop_id"]]["withdrawn"]]
    if params.get("urgent_only"):
        needs = [n for n in needs if n["urgency"] == "urgent"]

    quotes, quote_options = {}, {}
    for r in conn.execute("SELECT * FROM supplier_quotes ORDER BY price_paise, id"):
        quotes.setdefault(r["product_id"], r["price_paise"])
        quote_options.setdefault(r["product_id"], []).append(dict(r))

    names = {r["id"]: dict(r) for r in conn.execute(
        "SELECT id, name, name_hi, emoji, pack_size, unit FROM products")}

    ctx = {
        "shops": shops, "needs": needs, "quotes": quotes, "quote_options": quote_options,
        "names": names, "lots": lots,
        "today": today, "min_shelf_default": min_shelf_default, "radius": radius,
        "params": params,
    }
    ctx["pair_edges"] = build_edges(ctx)
    return ctx


def build_edges(ctx: dict) -> dict:
    """Candidate give/receive edges grouped per ordered shop pair, best products first."""
    today, radius = ctx["today"], ctx["radius"]
    shops, needs, lots = ctx["shops"], ctx["needs"], ctx["lots"]
    pair_edges = {}   # (giver, receiver) -> [Edge]
    distances, eligibility = {}, {}
    for n in needs:
        r = n["shop_id"]
        if shops[r]["withdrawn"] or not shops[r].get("sharing_opt_in", 1):
            continue   # a withdrawn participant neither gives, receives, nor buys in re-plans
        candidates = {}   # giver -> [Edge]
        for g, s in shops.items():
            if g == r or s["withdrawn"] or not s.get("sharing_opt_in", 1):
                continue
            pair = tuple(sorted((g, r)))
            if pair not in distances:
                distances[pair] = haversine_km(s["lat"], s["lng"], shops[r]["lat"], shops[r]["lng"])
            d = distances[pair]
            if d > radius:
                continue
            for p in dict.fromkeys([n["product_id"]] + n["alts"]):
                key = (g, p, n["min_shelf_days"])
                if key not in eligibility:
                    eligibility[key] = eligible_lots(lots, g, p, n["min_shelf_days"], today)
                ls = eligibility[key]
                if not ls:
                    continue
                avail = sum(_free_qty(l) for l in ls)
                value = sum(l["cost_paise"] * _free_qty(l) for l in ls) // avail
                candidates.setdefault(g, []).append(Edge(
                    giver=g, receiver=r, need_id=n["id"], product_id=p,
                    max_qty=min(avail, n["qty"]), unit_value_paise=value,
                    dist_km=d, slow=any(l["slow"] for l in ls),
                    min_shelf_days=n["min_shelf_days"]))
        for g, es in candidates.items():
            es.sort(key=lambda e: e.max_qty * e.unit_value_paise, reverse=True)
            pair_edges.setdefault((g, r), []).extend(es)
    for pair, edges in pair_edges.items():
        edges.sort(key=lambda e: (-e.max_qty * e.unit_value_paise, e.need_id, e.product_id))
        if len(edges) > MAX_PRODUCTS_PER_PAIR:
            ctx["candidate_truncated"] = True
        pair_edges[pair] = edges[:MAX_PRODUCTS_PER_PAIR]
    return pair_edges


def eligible_lots(lots: dict, giver: int, product_id: int, min_shelf_days: int, today) -> list:
    out = []
    for lot in lots.get((giver, product_id), []):
        if not lot["permit_share"] or lot["condition"] != "sealed" or lot["cost_paise"] <= 0:
            continue
        days = days_to_expiry(lot.get("expiry_date"), today)
        if days is None or days < min_shelf_days:
            continue
        if _free_qty(lot) > 0:
            out.append(lot)
    return out


def enumerate_cycles(ctx: dict, max_len: int = 3) -> list[Cycle]:
    """Feasible 2- and 3-shop exchange cycles (v1 excludes 4+ shops)."""
    pe = ctx.get("pair_edges") or build_edges(ctx)
    ctx["pair_edges"] = pe
    cycles: list[Cycle] = []
    seen = set()

    def add(legs):
        mx = min(e.max_qty for e in legs)
        if mx <= 0 or len({e.product_id for e in legs}) < len(legs):
            return
        key = tuple(sorted((e.giver, e.receiver, e.need_id, e.product_id) for e in legs))
        if key in seen:
            return
        seen.add(key)
        cycles.append(Cycle(legs=tuple(legs), max_qty=mx, key=key))

    def candidates():
        for (a, b), e_ab in sorted(pe.items()):
            if a < b:
                yield from product(e_ab, pe.get((b, a), []))
        if max_len >= 3:
            shops = sorted({a for a, _ in pe} | {b for _, b in pe})
            for a, b, c in combinations(shops, 3):
                for x, y, z in ((a, b, c), (a, c, b)):
                    if (x, y) in pe and (y, z) in pe and (z, x) in pe:
                        yield from product(pe[x, y], pe[y, z], pe[z, x])

    for legs in candidates() if max_len >= 2 else []:
        add(legs)
        if len(cycles) >= MAX_CYCLES:
            ctx["candidate_truncated"] = True
            break

    cycles.sort(key=lambda c: c.max_qty * sum(e.unit_value_paise for e in c.legs), reverse=True)
    return cycles
