# ShelfLoop

A local, bilingual prototype for Tech4Bharat PS 5.1: help kirana owners capture stock, express needs and approve a costed replenishment or two-/three-shop exchange.

**Current evidence:** synthetic-data application and automated evaluation. Field interviews, the seven-day shadow pilot, live commercial transfers and hackathon submission have not been completed. See [verification](docs/VERIFICATION.md) for exact checks and limits.

## Run on Windows

Use Python 3.12 (recommended; 3.10+ syntax is required). The built frontend is included.

```powershell
.\run.bat
```

Open http://127.0.0.1:8000. Demo operator PIN: **0000**. Demo owner PIN: **1234**.
These shared PINs are for local synthetic demonstrations, not public production authentication.
Sessions are isolated per browser tab, so separate tabs can demonstrate separate owners.

The launcher creates a virtual environment and checks the required packages. A first setup requires internet; models are never silently downloaded. Subsequent use with installed dependencies is local.

Manual equivalent:

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Startup seeds an empty database only. Existing data is preserved. To use a separate fresh synthetic database without overwriting an existing one:

```powershell
$env:SHELFLOOP_DB_PATH = Join-Path $PWD "data/fresh-demo.db"
.\run.bat
```

The legacy seed command `python -m app.seed` force-resets the selected database. Use it only for a disposable synthetic dataset.

## Main workflows

- **Owner:** Today, Stock, Needs, Approvals. Set the shop cash limit and sharing consent under Needs. Capture typed/spoken text or an invoice, review catalogue matches and whole-pack quantities, and explicitly confirm.
- **Stock:** edit quantity, confirmed purchase cost and label date. New captures remain private with unknown cost until the owner supplies missing details; unknown cost is not invented from MRP.
- **Operator:** Overview, Planning, Exchange graph, Failure rehearsal, Evidence.
- **Planning:** default focus is the three crafted demo shops. Disable that checkbox to test all 25 shops. Historical plan IDs are clickable; the active plan is restored in the operator tab after reload.
- **Approvals:** submit a proposal to acquire stock/cash holds. Every participant approves using its own owner session. The operator cannot approve for an owner. Dispatch remains a sandbox operation.
- **Recovery:** withdrawal, reduced stock and disconnection are simulated explicitly. Old approvals do not authorise a changed plan. Partial handoffs require operator review and do not fulfil undelivered needs.

## What actually runs

| Capability | Current implementation |
|---|---|
| Planning | Local OR-Tools CP-SAT, exact lexicographic priorities, time-bounded solving |
| Lifecycle | SQLite transactions, source/version checks, stock/cash holds, deadlines and concurrent-dispatch protection |
| Text capture | Hindi/English aliases and counts, ambiguity questions, explicit confirmation |
| Invoice upload | Actual TXT/CSV and text-PDF extraction with limits and validation |
| Local image OCR | Adapter implemented; requires optional Tesseract and Hindi/English language data |
| Local audio upload | Adapter implemented; requires optional Faster-Whisper and a cached multilingual model |
| Browser microphone | Web Speech where supported; browser/network dependent, not guaranteed offline |
| Ollama | Optional capture enrichment; no model runtime is bundled or required for deterministic operation |
| Offline | Cached application/route assets, owner-scoped text drafts and retryable capture-confirmation outbox |
| External integrations | Supplier acknowledgements, immediate receipts and handoffs are labelled simulations |

[Capture runtime setup and limits](docs/capture-runtime.md) explains supported files and optional free local engines. Health diagnostics at `GET /api/health` expose installed capture capabilities.

## Design and frontend

The design contract is [DESIGN.md](DESIGN.md). The interface uses forest green, mint and a warm neutral canvas, local fonts, keyboard focus, reduced-motion handling and mobile stock cards.

```powershell
cd frontend
npm ci
npm run build
npm run lint
node --test scripts/outbox.test.mjs
npm run dev
```

The frontend always uses same-origin `/api`, including phone/tunnel sessions. Development proxies to port 8000. A production build generates a versioned precache manifest for all route assets. Offline drafts work after first load; planning, inference and final approvals require the backend. Clearing browser/site data removes device-local drafts.

For a supervised phone demonstration, use a temporary HTTPS tunnel with synthetic data and the backend running. No tunnel, public hosting or production deployment is configured automatically.

## Planning model

1. Maximise owner-confirmed, urgency-weighted need coverage.
2. Minimise additional cash: purchases, positive balancing obligations and transport.
3. Prefer redeploying confirmed slow stock.
4. Minimise transport burden.

Money is integer paise and quantities are whole packs. Negative balancing receipts never finance new purchases. Transport shares preserve every paise. Supplier minimum order quantities are enforced without overfilling a need.

Constraints cover stock floors, reservations, sharing consent, sealed condition, known positive transfer costs, confirmed dates, shelf-life thresholds, distance and shop budgets. Alternative products must be explicitly permitted. Only two-/three-shop cycles are enumerated; all legs in one cycle currently use the same pack count, and each shop can join at most one selected cycle per run.

`OPTIMAL` means optimal within the enumerated model. A time-limited feasible result is not presented as proven optimal. Unknown/failed search is not proof of infeasibility.

## Reproducible evaluation

```powershell
.\backend\.venv\Scripts\python.exe evaluation/generate_scenarios.py
.\backend\.venv\Scripts\python.exe evaluation/run_baselines.py
.\backend\.venv\Scripts\python.exe evaluation/benchmark_planner.py
```

All four strategies receive identical stock, needs, budgets and supplier quotes. The manual baseline is a deterministic purchasing heuristic, not observed shopkeeper behaviour.

Across the saved 100 artificial scenarios:

| Strategy | Mean coverage | Gross cash required |
|---|---:|---:|
| Manual purchasing heuristic | 80.0% | ₹480.59 |
| Replenishment only | 80.0% | ₹480.59 |
| Pairwise exchanges | 80.0% | ₹414.29 |
| ShelfLoop two-/three-shop cycles | 80.0% | ₹379.47 |

The identical per-need fulfilment comparison yields **21.0% lower simulated gross cash than purchasing** and **8.4% lower than pairwise exchange**. These replace the earlier inflated 42%/52% claims: transport is included and manual supplier prices are no longer marked up artificially.

[Report](evaluation/report.md), [results](evaluation/results.csv), [solver timings](evaluation/performance.json).

Inventory redeployed is not cash released. Avoided expenditure is not measured savings. Scenario proportions are artificial and do not establish adoption or commercial ROI. The corrected solver does more work than the original incorrect objective; do not describe old/new timing as an equal-quality speedup.

## Backend verification

```powershell
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q --basetemp backend/.pytest-tmp-check
```

Tests cover solver/exhaustive agreement, budget/stock conservation, sharing and date boundaries, auth isolation, malformed input, replay/idempotency, expired and changed approvals, cash holds, concurrency, partial delivery, capture and real PDF/text parsing. Test databases remain separate from the running demo.

## HTTP interfaces

[API contract](docs/api-contract.md) documents the current surface. Key interfaces:

- `GET/PATCH /api/shops/{shop_id}/preferences`: own cash/sharing settings with version checks.
- `POST /api/captures/audio|invoice`: multipart `shop_id` and `file`; up to 8 MiB.
- Existing-lot inventory edits require `expected_version`.
- Planning parameters accept optional `shop_ids` for a selected cluster.
- Inventory/capture idempotency keys are scoped to actor and operation; conflicting reuse is rejected.
- Full stock/needs are own-shop or operator only; cluster analytics are operator only.
- Missing API routes return JSON 404 rather than the SPA shell.

## Delivery boundaries

The app does not move money, contact real suppliers, determine food safety, decide tax treatment, or perform real transfers. The 14-day default is a planning parameter. Some shadow-pilot and submission deliverables still require real people and event-portal access; use [verification](docs/VERIFICATION.md) as the completion checklist.
