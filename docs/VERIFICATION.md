# Completion and verification

Checked locally on 25 October 2026. This is a working synthetic-data prototype. The field pilot, optional model runtimes and event submission remain separate unfinished work.

## Verified checks

| Check | Observed result |
|---|---|
| Backend pytest | **126 passed** in 31.48 s; one upstream Starlette/httpx deprecation warning |
| Frontend `npm test` | **7 passed**: owner isolation, duplicate replay, network/server failure, conflicts, concurrent replay, newly queued work and storage failure |
| Frontend `npm run build` | TypeScript and Vite production build passed; offline precache generated |
| Frontend `npm run lint` | Passed with warnings denied |
| Font assets | 1,239,904 → 477,752 bytes, **61.5% smaller**, retaining local Hindi fonts |
| Dense planner fixture | 25 shops, 375 lots, 75 needs, 450 cycles: median **2,384.03 ms**, three OPTIMAL runs |
| Synthetic evaluation | 100 scenarios with identical per-need fulfilment: **21.0%** lower gross cash vs purchase-only, **8.4%** vs pairwise |

The previous solver was faster but optimized an incorrect objective; timing is not an equal-quality speed comparison. Synthetic percentages are scenario results, not measured shop savings. See [evaluation report](../evaluation/report.md) and [performance data](../evaluation/performance.json).

## Browser flows actually exercised

Review instance: `http://127.0.0.1:8001`, separate `data/review-demo.db`. Existing primary demo data was preserved.

1. Signed in as operator; loaded cluster metrics and the paginated/searchable shop directory.
2. Planned shops 1–3. OPTIMAL, 55/55 needed packs covered, one three-shop cycle and three purchase lines.
3. Requested ten-minute stock/cash holds. Signed into three independent owner tabs, reviewed the full receipt and approved as each owner.
4. Reloaded operator: exact plan and approval history restored. Sandbox dispatch became **COMPLETED**, with three transfer and three supplier-order acknowledgements. Owner needs became zero and cash fell by the full obligation.
5. Opened narrow-screen stock, expanded quantity/cost/date controls, and successfully saved owner cash/sharing preferences.
6. Typed `Maggi 70g 5 packs`, reviewed the parsed five-pack proposal, then explicitly confirmed it. A private five-pack lot appeared with unconfirmed cost/date, excluded from exchanges.
7. Switched owner stock to Hindi; verified translated product cards, controls and navigation. Desktop overview was observed at 1,270 CSS px; narrow owner view at 317 CSS px, with equal document/client widths (no page overflow). The requested 390 px override was scaled by the visible preview host; this is not an exact 390 px measurement.
8. Inspected exchange graph, keyboard-focusable shop controls, failure rehearsal and evidence. Failure-injection invariants and partial delivery were exercised in automated tests; every failure was not repeated in the browser.

Screenshots: [operator overview](screenshots/operator-overview.jpg), [Hindi owner stock](screenshots/owner-stock-hindi.jpg), [exchange graph](screenshots/exchange-graph.jpg).

Browser checks exposed and corrected receipt bugs: external spend compared with gross cash, pack counts labelled as grams, and approval-history fields crashing the receipt after approval. A recovery screen now handles load/render failures. A stale-tab asset failure during local rebuilding was recovered by reload; open tabs can encounter the recovery screen when builds change.

## Completed in the local prototype

- Redesigned owner/operator workspaces and sign-in, shared design tokens, responsive stock cards, Hindi/English, keyboard focus and reduced-motion styles.
- Explicitly confirmed stock capture, ambiguous-count handling, manual lot editing, needs and owner cash/sharing preferences.
- Owner-scoped drafts/outbox, idempotent writes, same-origin API and versioned shell precache. New offline text drafts need reconnection for server parsing; approvals require the server.
- Two/three-shop cycles, purchases, exact staged optimization, conservative budgets, stock/cash holds, source-version checks, expiry and independent owner approvals.
- Atomic sandbox dispatch, simulated inventory receipts, partial-handoff exceptions, audit events, export and failure rehearsal.
- Regression tests for auth boundaries, malformed writes, concurrency/replay, lifecycle changes, exhaustive solver agreement, capture and actual text/PDF parsing.
- Launchers, dependency snapshot, current API contract, corrected evaluation and design source of truth.

## Remaining setup and validation

- **Optional OCR/speech/model runtime:** adapters and manual fallback states exist. Tesseract, multilingual Whisper and Ollama were not installed/runtime-validated. TXT/CSV and text PDF work. Browser microphone/physical-device behavior and guaranteed offline speech are unverified. See [runtime details](capture-runtime.md).
- **Field work:** 3–5 shop visits, confirmed terminology/costs, consented records, seven-day shadow pilot, measured expiry/stockout outcomes and willingness to participate/pay.
- **Real integrations:** supplier delivery, transport, payments, messaging, food-safety and tax processes remain outside the sandbox. Production identity/privacy/hosting work is required for real shops.
- **Submission:** final deck/video, four-person eligibility, current rules/deadlines, portal registration and uploads require separate verification. No submission or public deployment was performed.

Planner limits: at most one selected cycle per shop, two/three-shop cycles only, equal pack counts across cycle legs. No forecast accuracy or worldwide novelty is claimed. Browser observations and targeted tests are not a complete physical-device or accessibility certification.

## Repeat checks

From the project root in PowerShell:

```powershell
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
.\backend\.venv\Scripts\python.exe -m pytest backend/tests -q --basetemp backend/.pytest-tmp-check
```

From `frontend/`: `npm test`, `npm run build`, `npm run lint`. Run `run.bat` for the normal demo on port 8000. The review instance on 8001 is process-local and may need restarting in a later session. Launchers install declared dependencies when needed and preserve the database.
