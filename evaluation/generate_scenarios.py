"""Generates 100 reproducible synthetic planning scenarios: cooperative clusters,
unfavourable cases (no reciprocal surplus), and impossible cases (no stock at all).
Used by run_baselines.py; kept separate from prompt-development examples."""
import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent / "scenarios.json"


def scenario(rng: random.Random, idx: int) -> dict:
    n_shops = rng.randrange(3, 9)
    kind = ("cooperative" if idx % 5 in (0, 1, 2) else
            "unfavourable" if idx % 5 == 3 else "impossible")
    n_products = rng.randrange(3, 8)
    shops = {}
    for s in range(1, n_shops + 1):
        shops[s] = {"lat": rng.uniform(-0.01, 0.01), "lng": rng.uniform(-0.01, 0.01),
                    "cash_limit_paise": rng.randrange(5, 40) * 10000}
    lots, needs = {}, []
    pid_base = 100
    if kind != "impossible":
        for s in range(1, n_shops + 1):
            for _ in range(rng.randrange(1, 4)):
                prod = pid_base + rng.randrange(n_products)
                lots[(s, prod)] = {"qty": rng.randrange(4, 20), "cost_paise": rng.randrange(200, 5000),
                                   "slow": 1 if rng.random() < 0.3 else 0}
    if kind == "cooperative":
        # ensure at least one reciprocal need so exchanges are possible
        prods = list({p for _s, p in lots} | {pid_base + i for i in range(n_products)})
        for s in range(1, n_shops + 1):
            other = s % n_shops + 1
            have_other = [p for (g, p) in lots if g == other]
            if have_other and rng.random() < 0.9:
                needs.append({"shop": s, "product": rng.choice(have_other),
                              "qty": rng.randrange(2, 8),
                              "urgency": rng.choice(["urgent", "normal"])})
    elif kind == "unfavourable":
        # needs exist but point at products nobody holds
        for s in range(1, n_shops + 1):
            needs.append({"shop": s, "product": pid_base + 50 + rng.randrange(n_products),
                          "qty": rng.randrange(2, 6), "urgency": "normal"})
    else:  # impossible: needs with no stock anywhere and no quote
        for s in range(1, n_shops + 1):
            needs.append({"shop": s, "product": pid_base + 90 + rng.randrange(n_products),
                          "qty": rng.randrange(2, 6), "urgency": "urgent"})
    quotes = {}
    for p in {q for _s, q in lots} | {n["product"] for n in needs}:
        quotes[p] = rng.randrange(300, 6000)
    if kind == "impossible":
        quotes = {p: pr for p, pr in quotes.items() if p not in {n["product"] for n in needs}}
    return {"id": idx, "kind": kind, "shops": shops,
            "lots": [{"shop": s, "product": p, **v} for (s, p), v in lots.items()],
            "needs": needs, "quotes": quotes}


def main():
    rng = random.Random(2026)
    scenarios = [scenario(rng, i) for i in range(100)]
    OUT.write_text(json.dumps(scenarios, indent=1))
    kinds = {}
    for s in scenarios:
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    print(f"wrote {len(scenarios)} scenarios to {OUT}: {kinds}")


if __name__ == "__main__":
    main()
