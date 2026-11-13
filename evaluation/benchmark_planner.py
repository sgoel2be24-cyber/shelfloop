"""Reproducible solver benchmark; optional original implementation from git HEAD.

Both implementations receive the same current, retained candidate graph. This
measures solver wall time, not production throughput or equal decision quality.
"""
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'evaluation'))
from app.planner import enumerate_cycles
from app.planner.solve import solve_model
from run_baselines import to_ctx


def fixture(n_shops=25, seed=2026):
    rng = random.Random(seed)
    quotes = {p: rng.randrange(500, 6000) for p in range(100, 200)}
    shops = {s: {'lat': rng.uniform(0, .006), 'lng': rng.uniform(0, .006),
                 'cash_limit_paise': 250000} for s in range(1, n_shops+1)}
    lots = []
    stock = {}
    for s in shops:
        stock[s] = rng.sample(list(quotes), 15)
        lots.extend({'shop': s, 'product': p, 'qty': rng.randrange(5, 15),
                     'cost_paise': quotes[p]*4//5, 'slow': int(rng.random()<.4)}
                    for p in stock[s])
    needs = []
    for s in shops:
        available_elsewhere = sorted({p for other in shops if other != s for p in stock[other]} - set(stock[s]))
        for p in rng.sample(available_elsewhere, min(3, len(available_elsewhere))):
            needs.append({'shop': s, 'product': p, 'qty': rng.randrange(2, 6),
                          'urgency': rng.choice(['normal', 'urgent'])})
    return to_ctx({'shops': shops, 'lots': lots, 'needs': needs, 'quotes': quotes})


def original_solver():
    source = subprocess.run(['git', 'show', 'HEAD:backend/app/planner/solve.py'], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8')
    if source.returncode:
        return None
    namespace = {'__name__': 'app.planner._baseline_solver', '__package__': 'app.planner'}
    exec(compile(source.stdout, '<baseline-solver-at-git-HEAD>', 'exec'), namespace)
    return namespace['solve_model']


def main():
    previous = original_solver()
    rows = []
    for size in (5, 10, 25):
        ctx = fixture(size)
        t0 = time.perf_counter()
        cycles = enumerate_cycles(ctx)
        enum_ms = (time.perf_counter()-t0)*1000
        row = {'shops': size, 'catalogue_products': 100, 'lots': sum(map(len,ctx['lots'].values())),
               'needs': len(ctx['needs']), 'candidate_cycles': len(cycles),
               'enumeration_ms': round(enum_ms, 2)}
        for label, solver in [('before', previous), ('after', solve_model)]:
            if solver is None:
                continue
            samples, statuses = [], []
            for _ in range(3):
                start = time.perf_counter()
                result = solver(cycles, ctx, 5000)
                samples.append((time.perf_counter()-start)*1000)
                statuses.append(result['status'])
            row[label+'_median_ms'] = round(statistics.median(samples), 2)
            row[label+'_statuses'] = statuses
        rows.append(row)
    out = ROOT/'evaluation'/'performance.json'
    out.write_text(json.dumps({'fixture_seed':2026, 'repeats':3,
        'baseline':'git HEAD solver source, same retained graphs; original correctness defects remain',
        'results':rows}, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
