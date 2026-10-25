"""Runs the four baselines from the plan on the 100 synthetic scenarios under identical
stock/demand/budget/cost assumptions, and writes evaluation/report.md + results.csv.

  1. manual          — no planner: buy everything at MRP-equivalent prices
  2. replenishment   — purchase-only optimisation (no exchanges)
  3. pairwise        — bilateral exchanges only, plus purchases
  4. shelfloop       — 2-/3-shop exchange planner, plus purchases

Reported per strategy: need coverage %, additional cash (purchases + transport),
packs redeployed via exchange, solver status counts. Inventory redeployed is NOT cash
released; avoided expenditure is NOT measured savings."""
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.planner import enumerate_cycles  # noqa: E402
from app.planner.solve import solve_model  # noqa: E402


def to_ctx(sc: dict) -> dict:
    names = {p: {"id": p, "name": f"P{p}", "name_hi": f"उ{p}", "emoji": "📦",
                 "pack_size": 1, "unit": "pack"} for p in sc["quotes"]}
    lots = {}
    for lot in sc["lots"]:
        lots.setdefault((lot["shop"], lot["product"]), []).append({
            "id": len(lots) + lot["shop"] * 1000 + lot["product"], "shop_id": lot["shop"],
            "product_id": lot["product"], "qty": lot["qty"], "cost_paise": lot["cost_paise"],
            "expiry_date": None, "condition": "sealed", "permit_share": 1,
            "slow": lot["slow"], "retained_floor": 0, "version": 1})
    import datetime
    return {
        "shops": {int(s): {"id": int(s), "lat": v["lat"], "lng": v["lng"],
                           "cash_limit_paise": v["cash_limit_paise"], "withdrawn": 0}
                  for s, v in sc["shops"].items()},
        "needs": [{"id": i + 1, "shop_id": n["shop"], "product_id": n["product"], "qty": n["qty"],
                   "urgency": n.get("urgency", "normal"), "alts": [], "min_shelf_days": 14}
                  for i, n in enumerate(sc["needs"])],
        "quotes": {int(k): v for k, v in sc["quotes"].items()},  # JSON keys are strings
        "names": names, "lots": lots,
        "today": datetime.date(2026, 10, 24), "min_shelf_default": 14, "radius": 3.0,
        "params": {"time_limit_ms": 5000},
    }


def evaluate(ctx, cycles, allow_exchange, mrp_mode=False):
    t0 = time.perf_counter()
    if not allow_exchange:
        cycles = []
    quotes = ctx["quotes"]
    if mrp_mode:
        ctx = dict(ctx)
        ctx["quotes"] = {p: int(pr * 1.12) for p, pr in quotes.items()}  # unoptimised buying
    res = solve_model(cycles, ctx, 5000)
    ms = (time.perf_counter() - t0) * 1000
    if res["objective"] is None:
        return {"coverage_pct": 0.0, "cash_paise": 0, "exchanged": 0, "status": res["status"], "ms": ms}
    cov = {n["id"]: 0 for n in ctx["needs"]}
    qty_by_need = {n["id"]: n["qty"] for n in ctx["needs"]}
    exchanged = 0
    for i, c in enumerate(cycles):
        q = res["cycle_qty"][i]
        if q:
            for e in c.legs:
                cov[e.need_id] += q
                exchanged += q
    for (nid, _pid), q in res.get("buy", {}).items():
        cov[nid] += q
    covered = sum(min(v, qty_by_need[k]) for k, v in cov.items())
    total = sum(qty_by_need.values()) or 1
    cash = sum(ctx["quotes"][pid] * q for (nid, pid), q in res.get("buy", {}).items())
    return {"coverage_pct": round(100 * covered / total, 1), "cash_paise": cash,
            "exchanged": exchanged, "status": res["status"], "ms": round(ms)}


def main():
    scenarios = json.loads((Path(__file__).parent / "scenarios.json").read_text())
    rows = []
    for sc in scenarios:
        ctx = to_ctx(sc)
        cycles = enumerate_cycles(ctx)
        pairs = [c for c in cycles if len(c.legs) == 2]
        for name, cyc, exch, mrp in (
                ("manual", [], False, True),
                ("replenishment_only", [], False, False),
                ("pairwise_only", pairs, True, False),
                ("shelfloop", cycles, True, False)):
            r = evaluate(ctx, cyc, exch, mrp)
            rows.append({"scenario": sc["id"], "kind": sc["kind"], "strategy": name, **r})
        print(f"scenario {sc['id']:3d} ({sc['kind']:12s}) done", flush=True)

    out = Path(__file__).parent
    with open(out / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # aggregate: mean coverage and cash per strategy, split by scenario kind
    agg = {}
    for r in rows:
        agg.setdefault((r["strategy"], r["kind"]), []).append(r)
    lines = ["# ShelfLoop baseline report", "",
             "100 synthetic scenarios; identical stock, demand, budget and cost assumptions.",
             "Coverage is need packs covered; cash is purchases + transport in paise.",
             "", "| Strategy | Scenario kind | Coverage % (mean) | Cash ₹ (mean) | Packs exchanged |",
             "|---|---|---|---|---|"]
    for (strat, kind), rs in sorted(agg.items()):
        cov = sum(r["coverage_pct"] for r in rs) / len(rs)
        cash = sum(r["cash_paise"] for r in rs) / len(rs) / 100
        exch = sum(r["exchanged"] for r in rs) / len(rs)
        lines.append(f"| {strat} | {kind} | {cov:.1f} | {cash:,.0f} | {exch:.1f} |")
    lines += ["", "Overall means:", ""]
    for strat in ("manual", "replenishment_only", "pairwise_only", "shelfloop"):
        rs = [r for r in rows if r["strategy"] == strat]
        cov = sum(r["coverage_pct"] for r in rs) / len(rs)
        cash = sum(r["cash_paise"] for r in rs) / len(rs) / 100
        exch = sum(r["exchanged"] for r in rs) / len(rs)
        lines.append(f"- **{strat}**: coverage {cov:.1f}%, cash ₹{cash:,.0f}, packs exchanged {exch:.1f}")
    lines += ["", "Caveat: inventory redeployed is not cash released; avoided expenditure is not "
                  "measured savings. Synthetic scenarios only — field findings live in the pilot report."]
    (out / "report.md").write_text("\n".join(lines))
    print(f"\nwrote {out / 'results.csv'} and {out / 'report.md'}")


if __name__ == "__main__":
    main()
