# ShelfLoop API contract

Updated 25 October 2026. The frontend uses same-origin `/api`. The running backend exposes the full generated schema at `/docs` and `/openapi.json`. Money is integer paise; quantities are whole packs, even when a catalogue unit describes weight/volume.

## Access

`POST /api/session {role: "owner"|"operator", shop_id?, pin}` returns a bearer token. Synthetic credentials: operator `0000`, owners `1234`; these are demo authentication, unsuitable for production.

Owners access only their stock, needs, preferences, captures and participating plans. Only the relevant owner can approve/reject. Operators plan, submit, cancel, dispatch, view cluster analytics/evidence and inject sandbox failures. Public shop discovery supports sign-in; other shops' cash limits are omitted from public/owner directory results.

## Stock, needs and settings

```text
GET /api/shops
GET /api/products
GET /api/shops/{id}/stock
GET /api/shops/{id}/needs
GET /api/shops/{id}/pulse
GET /api/shops/{id}/expiry-actions
GET /api/shops/{id}/plans
GET /api/supplier-quotes?product_id=...
POST /api/needs
DELETE /api/needs/{id}
POST /api/supplier-quotes
```

Stock rows expose `lot_id`, product identity, qty, reserved/available quantities, retained floor, cost, date, condition/sharing/slow flags and version. Unknown cost uses zero as a sentinel, not an estimate. Unpriced and undated lots are excluded from exchanges.

`POST /api/needs` accepts `{shop_id, product_id, qty, urgency?, alt_product_ids?, budget_paise?, min_shelf_days?}`. The budget is a maximum unit price. Quotes accept `{product_id, supplier_name, price_paise, min_order_packs?, lead_days?}`.

`POST /api/inventory/confirm` accepts `{shop_id, changes:[{product_id, lot_id?, expected_version?, qty?, delta?, cost_paise?, expiry_date?, condition?, permit_share?, slow?, retained_floor?}], reason?}`. Existing lots require `expected_version`; stale writes return 409. Use absolute qty or delta, never both. New lots require qty and default private. The batch is atomic. Optional `Idempotency-Key` is scoped to actor and operation; identical retry replays, conflicting reuse returns 409.

`GET /api/shops/{id}/preferences` returns `{shop_id, version, cash_limit_paise, sharing_opt_in, held_cash_paise}`. The own-shop owner can PATCH `{expected_version, cash_limit_paise, sharing_opt_in}`. Limits below existing holds are rejected. Purchases, transport and outgoing balancing payments consume cash. Incoming balancing money cannot finance purchases in advance.

## Capture: propose, review, confirm

```text
POST /api/captures {shop_id, text}
POST /api/captures/invoice  multipart: shop_id, file
POST /api/captures/audio    multipart: shop_id, file
POST /api/captures/{id}/confirm {edits:[{index, product_id, qty, unit, kind, cost_paise?}]}
```

Proposals return capture_id, status, engine and rows. Ambiguous products/counts need explicit owner resolution. Confirm uses positive integer pack counts, atomically confirms once, and supports scoped Idempotency-Key. New stock stays private with unknown cost/date unless provided.

Uploads are limited to 8 MiB. TXT/CSV/text PDFs work. Optional image/audio engines return failed with `fallback:"manual-form"` when unavailable. Malformed media returns 422; oversized media 413. See [capture runtime](capture-runtime.md).

## Planning and lifecycle

`POST /api/planning-runs {case_id:"cluster-main",params?:{shop_ids?:[1,2,3],time_limit_ms?:5000,min_shelf_days?:14,radius_km?:3,include_purchases?:true,urgent_only?:false}}` returns run_id. Poll GET `/api/planning-runs/{run_id}` for queued/running/done/error, progress, log, solver and plan_id. Omit shop_ids to use all shops. A timeout is UNKNOWN/FEASIBLE, never fabricated INFEASIBLE. Candidate truncation is disclosed. Interrupted runs become errors on restart.

```text
GET /api/plans/{id}
GET /api/plans/{id}/status
POST /api/plans/{id}/submit
POST /api/plans/{id}/approve
POST /api/plans/{id}/reject {reason}
POST /api/plans/{id}/cancel
POST /api/plans/{id}/dispatch
```

Normal path: PROPOSED -> AWAITING_APPROVAL -> APPROVED -> COMPLETED through sandbox dispatch. Alternatives: REJECTED, EXPIRED, CANCELLED, NEEDS_OPERATOR. Submission atomically holds stock/cash for ten minutes, including purchase-only plans. Each affected owner approves the immutable plan/version. Source shop/stock/need/quote versions and deadline are checked at dispatch. Repeated/concurrent dispatch cannot execute twice. Material changes require a fresh plan and approvals.

Receipts contain id, version, status, creation/deadline, fingerprint, participants, cycles, purchases, coverage, costs, assumptions, solver, comparisons and approval_history. Cycle fields include legs, shop_path, balancing_paise_by_shop, transport_paise and exact transport_by_shop_paise. Rounded transport_per_shop_paise is informational only. Leg qty is always packs.

Positive balancing means pays; negative means owed. `costs.cash_out_by_shop` is nonnegative cash needed per owner; gross_cash_out_paise sums it. external_cash_paise is purchases plus transport; balancing_cash_paise is outgoing balancing cash. All comparison bars use gross cash consistently.

Approval history exposes shop_id, decision, decided_at, alias at, and the immutable plan inputs_hash in both owner discovery and full receipts. Status includes reservations, approvals, approvals_missing and sandbox actions.

## Sandbox and evidence

```text
POST /api/sandbox/inject {type:"withdraw_shop"|"reduce_stock"|"disconnect",shop_id,product_id?,qty?}
POST /api/sandbox/reset
GET /api/sandbox/state
GET /api/cases/{id}/summary
GET /api/cases/{id}/directory
GET /api/cases/{id}/plans
GET /api/cases/{id}/events?limit=200
GET /api/cases/{id}/export
GET /api/health
```

Withdrawal/stock changes invalidate relevant plans at revalidation. Disconnection may cause a partial handoff. Only delivered quantities fulfil needs; unresolved obligations remain held for operator reconciliation. Supplier acknowledgement includes immediate simulated inventory receipt. Reset clears injected flags, not completed inventory changes. No real supplier, delivery or payment action occurs.

Health includes capture_capabilities. Export uses synthetic records and shop IDs; this is not a production privacy guarantee. APIs are network-only in the service worker. Errors use detail (string or validation list): 401 unauthenticated, 403 ownership/role, 404 missing, 409 conflicting/stale, 413 too large, 422 invalid input. Unknown API paths return JSON 404.
