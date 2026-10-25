"""Builds the planning world: availability, confirmed needs, candidate give/receive
edges and feasible 2-/3-shop cycles. Pure data; no solving here."""
import math
from dataclasses import dataclass, field
from datetime import date

from .. import db
from ..config import DEFAULT_MIN_SHELF_DAYS, DEFAULT_RADIUS_KM, MAX_PRODUCTS_PER_PAIR


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def days_to_expiry(expiry_iso: str | None, today: date) -> int | None:
    return (date.fromisoformat(expiry_iso) - today).days if expiry_iso else None


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
    total = 0
    for lot in ctx["lots"].get((giver, product_id), []):
        if not lot["permit_share"] or lot["condition"] != "sealed":
            continue
        if lot["expiry_date"] and days_to_expiry(lot["expiry_date"], ctx["today"]) < min_shelf_days:
            continue
        total += max(0, lot["qty"] - lot["retained_floor"])
    return total


def build_context(conn, params: dict) -> dict:
    """Snapshot of confirmed state used by every planner variant."""
    today = date.today()
    min_shelf_default = params.get("min_shelf_days", DEFAULT_MIN_SHELF_DAYS)
    radius = params.get("radius_km", DEFAULT_RADIUS_KM)

    shops = {}
    for r in conn.execute("SELECT * FROM shops"):
        shops[r["id"]] = dict(r)

    lots = {}   # (shop, product) -> [lot dicts]
    for r in conn.execute("SELECT * FROM stock_lots"):
        lots.setdefault((r["shop_id"], r["product_id"]), []).append(dict(r))

    needs = []
    for r in conn.execute("SELECT * FROM needs WHERE status='open'"):
        n = dict(r)
        n["alts"] = [int(x) for x in db.jload(r["alt_product_ids"], [])]
        n["min_shelf_days"] = r["min_shelf_days"] or min_shelf_default
        needs.append(n)
    needs = [n for n in needs if not shops[n["shop_id"]]["withdrawn"]]
    if params.get("urgent_only"):
        needs = [n for n in needs if n["urgency"] == "urgent"]

    quotes = {}
    for r in conn.execute("SELECT product_id, MIN(price_paise) price FROM supplier_quotes GROUP BY product_id"):
        quotes[r["product_id"]] = r["price"]

    names = {r["id"]: dict(r) for r in conn.execute(
        "SELECT id, name, name_hi, emoji, pack_size, unit FROM products")}

    ctx = {
        "shops": shops, "needs": needs, "quotes": quotes, "names": names, "lots": lots,
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
    for n in needs:
        r = n["shop_id"]
        if shops[r]["withdrawn"]:
            continue   # a withdrawn participant neither gives, receives, nor buys in re-plans
        candidates = {}   # giver -> [Edge]
        for g, s in shops.items():
            if g == r or s["withdrawn"]:
                continue
            d = haversine_km(s["lat"], s["lng"], shops[r]["lat"], shops[r]["lng"])
            if d > radius:
                continue
            for p in [n["product_id"]] + n["alts"]:
                ls = eligible_lots(lots, g, p, n["min_shelf_days"], today)
                if not ls:
                    continue
                avail = sum(l["qty"] - l["retained_floor"] for l in ls)
                value = int(sum(l["cost_paise"] * l["qty"] for l in ls) / sum(l["qty"] for l in ls))
                candidates.setdefault(g, []).append(Edge(
                    giver=g, receiver=r, need_id=n["id"], product_id=p,
                    max_qty=min(avail, n["qty"]), unit_value_paise=value,
                    dist_km=d, slow=any(l["slow"] for l in ls),
                    min_shelf_days=n["min_shelf_days"]))
        for g, es in candidates.items():
            es.sort(key=lambda e: e.max_qty * e.unit_value_paise, reverse=True)
            pair_edges.setdefault((g, r), []).extend(es[:MAX_PRODUCTS_PER_PAIR])
    return pair_edges


def eligible_lots(lots: dict, giver: int, product_id: int, min_shelf_days: int, today) -> list:
    out = []
    for lot in lots.get((giver, product_id), []):
        if not lot["permit_share"] or lot["condition"] != "sealed":
            continue
        if lot["expiry_date"] and days_to_expiry(lot["expiry_date"], today) < min_shelf_days:
            continue
        if lot["qty"] - lot["retained_floor"] > 0:
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

    for (a, b), e_ab in pe.items():
        for e1 in e_ab:
            for e2 in pe.get((b, a), []):
                if e1.product_id != e2.product_id:
                    add([e1, e2])

    if max_len >= 3:
        shops = sorted({a for a, _ in pe} | {b for _, b in pe})
        for i, a in enumerate(shops):
            for b in shops[i + 1:]:
                for c in shops[shops.index(b) + 1:]:
                    for path in ((a, b, c), (a, c, b)):
                        x, y, z = path
                        for e1 in pe.get((x, y), []):
                            for e2 in pe.get((y, z), []):
                                for e3 in pe.get((z, x), []):
                                    add([e1, e2, e3])

    cycles.sort(key=lambda c: c.max_qty * sum(e.unit_value_paise for e in c.legs), reverse=True)
    return cycles
