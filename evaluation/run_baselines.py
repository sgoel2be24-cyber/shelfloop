"""Fair synthetic baselines with identical quotes and full cash accounting.

No measured field outcomes are reported. The manual policy greedily purchases
needs in input order; it does not receive artificially inflated supplier prices.
"""
import csv
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.planner import enumerate_cycles
from app.planner.solve import _purchase_options, _result_cash, cycle_transport_paise, solve_model


def to_ctx(sc):
    product_ids = {int(p) for p in sc["quotes"]} | {n["product"] for n in sc["needs"]} | {l["product"] for l in sc["lots"]}
    names = {p: {"id": p, "name": f"P{p}", "name_hi": f"P{p}", "emoji": "box",
                 "pack_size": 1, "unit": "pack"} for p in product_ids}
    lots = {}
    for index, lot in enumerate(sc["lots"]):
        lots.setdefault((lot["shop"], lot["product"]), []).append({
            "id": index + 1, "shop_id": lot["shop"], "product_id": lot["product"],
            "qty": lot["qty"], "cost_paise": lot["cost_paise"],
            "expiry_date": lot.get("expiry_date", "2027-12-31"), "condition": "sealed",
            "permit_share": 1, "slow": lot["slow"], "retained_floor": 0, "version": 1})
    return {
        "shops": {int(s): {"id": int(s), "lat": v["lat"], "lng": v["lng"],
                           "cash_limit_paise": v["cash_limit_paise"], "withdrawn": 0, "sharing_opt_in": 1}
                  for s, v in sc["shops"].items()},
        "needs": [{"id": i + 1, "shop_id": n["shop"], "product_id": n["product"], "qty": n["qty"],
                   "urgency": n.get("urgency", "normal"), "alts": [], "min_shelf_days": 14}
                  for i, n in enumerate(sc["needs"])],
        "quotes": {int(k): v for k, v in sc["quotes"].items()},
        "names": names, "lots": lots,
        "today": date(2026, 10, 24), "min_shelf_default": 14, "radius": 3.0,
        "params": {"time_limit_ms": 5000},
    }


def manual_purchase(ctx):
    remaining = {s: v["cash_limit_paise"] for s, v in ctx["shops"].items()}
    buys, prices = {}, {}
    for need in ctx["needs"]:
        choices = sorted(_purchase_options(ctx, need), key=lambda q: (q[1], q[0], q[2]))
        for pid, price, minimum in choices:
            qty = min(need["qty"], remaining[need["shop_id"]] // price) if price else need["qty"]
            if qty >= minimum:
                key = (need["id"], pid)
                buys[key], prices[key] = qty, price
                remaining[need["shop_id"]] -= qty * price
                break
    return {"objective": 0, "buy": buys, "buy_prices": prices, "cycle_qty": [], "status": "HEURISTIC"}


def evaluate(ctx, cycles, allow_exchange=True, manual_mode=False):
    started = time.perf_counter()
    cycles = cycles if allow_exchange else []
    result = manual_purchase(ctx) if manual_mode else solve_model(cycles, ctx, 5000)
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    cov = {n["id"]: 0 for n in ctx["needs"]}
    exchanged = 0
    transport = 0
    for cycle, qty in zip(cycles, result.get("cycle_qty", [])):
        for edge in cycle.legs:
            cov[edge.need_id] += qty
            exchanged += qty
        transport += cycle_transport_paise(cycle, qty)
    for (nid, _), qty in result.get("buy", {}).items():
        cov[nid] += qty
    covered, total = sum(cov.values()), sum(n["qty"] for n in ctx["needs"])
    purchases = sum(result.get("buy_prices", {}).get((nid, pid), ctx["quotes"][pid]) * qty
                    for (nid, pid), qty in result.get("buy", {}).items())
    gross = _result_cash(ctx, cycles, result)
    return {"coverage_pct": round(100 * covered / total, 2) if total else 0,
            "cash_paise": gross, "external_cash_paise": purchases + transport,
            "transport_paise": transport, "exchanged": exchanged,
            "coverage_by_need": json.dumps(cov, sort_keys=True),
            "status": result["status"], "ms": elapsed}


def main():
    folder = Path(__file__).parent
    scenarios = json.loads((folder / "scenarios.json").read_text(encoding="utf-8"))
    rows = []
    for sc in scenarios:
        ctx = to_ctx(sc)
        cycles = enumerate_cycles(ctx)
        pairs = [c for c in cycles if len(c.legs) == 2]
        for name, subset, manual in (("manual", [], True), ("replenishment_only", [], False),
                                     ("pairwise_only", pairs, False), ("shelfloop", cycles, False)):
            rows.append({"scenario": sc["id"], "kind": sc["kind"], "strategy": name,
                         **evaluate(ctx, subset, manual_mode=manual)})

    with (folder / "results.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    lines = ["# ShelfLoop baseline report", "",
             f"{len(scenarios)} reproducible synthetic scenarios; no field outcomes.",
             "Every strategy receives identical stock, needs, budgets and supplier quotes.",
             "Manual means deterministic first-come purchasing, not an observed shopkeeper baseline.",
             "Gross cash includes purchases, positive balancing obligations and exact transport shares.",
             "External spend is purchases plus transport; it excludes cash paid between participating shops.",
             "Transport uses one call-out per selected cycle plus pack-distance charges.", "",
             "| Strategy | Scenario kind | Coverage % | Gross cash INR | External spend INR | Packs moved |",
             "|---|---|---:|---:|---:|---:|"]
    strategies = ("manual", "replenishment_only", "pairwise_only", "shelfloop")
    for strategy in strategies:
        for kind in sorted({r["kind"] for r in rows}):
            group = [r for r in rows if r["strategy"] == strategy and r["kind"] == kind]
            lines.append(f"| {strategy} | {kind} | {statistics.mean(r['coverage_pct'] for r in group):.1f} | "
                         f"{statistics.mean(r['cash_paise'] for r in group)/100:.2f} | "
                         f"{statistics.mean(r['external_cash_paise'] for r in group)/100:.2f} | "
                         f"{statistics.mean(r['exchanged'] for r in group):.1f} |")
    lines.extend(["", "## Overall means", ""])
    for strategy in strategies:
        group = [r for r in rows if r["strategy"] == strategy]
        lines.append(f"- **{strategy}**: coverage {statistics.mean(r['coverage_pct'] for r in group):.1f}%; "
                     f"gross cash INR {statistics.mean(r['cash_paise'] for r in group)/100:.2f}; "
                     f"external spend INR {statistics.mean(r['external_cash_paise'] for r in group)/100:.2f}; "
                     f"mean runtime {statistics.mean(r['ms'] for r in group):.2f} ms.")
    lines.extend(["", "## Equivalent-fulfilment comparison", ""])
    ours = {r["scenario"]: r for r in rows if r["strategy"] == "shelfloop"}
    for baseline in strategies[:-1]:
        pairs = [(r, ours[r["scenario"]]) for r in rows if r["strategy"] == baseline
                 and r["coverage_by_need"] == ours[r["scenario"]]["coverage_by_need"]]
        before = sum(a["cash_paise"] for a, b in pairs)
        after = sum(b["cash_paise"] for a, b in pairs)
        difference = f"{100 * (before-after)/before:.1f}%" if before else "not defined (zero cash baseline)"
        lines.append(f"- Versus {baseline}: {len(pairs)}/{len(scenarios)} identical per-need fulfilment cases; "
                     f"aggregate gross-cash reduction {difference}. Other cases are excluded from this cash comparison.")
    lines.extend(["", "## Limits", "",
                  "Candidate cycles are limited to two/three shops and one selected cycle per shop; all legs currently use the same pack count.",
                  "Generated cooperative/unfavourable/impossible case proportions are artificial, not observed market frequencies.",
                  "Statuses: " + json.dumps({s: sum(r["status"] == s for r in rows) for s in sorted({r['status'] for r in rows})}),
                  "Inventory redeployed is not cash released. Avoided expenditure is not measured savings.",
                  "Public synthetic fixtures make these results reproducible but do not establish adoption, commercial ROI or forecast accuracy."])
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-14:]))


if __name__ == "__main__":
    main()
