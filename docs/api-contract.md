# ShelfLoop API Contract v1

Base URL: `http://localhost:8000/api`. All endpoints return JSON unless noted.
Auth: `Authorization: Bearer <token>` from `POST /api/session`. Roles: `owner` (shop-scoped) and `operator`.
Server-side rule: **only an owner token for shop X can approve/reject on behalf of shop X; operator tokens are rejected on decision endpoints.**

Demo credentials: operator PIN `0000`; every owner PIN `1234`.

## Lifecycle (authoritative)

`PROPOSED → AWAITING_APPROVAL → APPROVED → SANDBOX_DISPATCHED → COMPLETED`
Terminal alternates: `REJECTED`, `EXPIRED`, `CANCELLED`, `NEEDS_OPERATOR`.

- Entering `AWAITING_APPROVAL` atomically reserves every leg's stock for **10 minutes**.
- Every affected owner must approve the exact plan version (`inputs_hash`).
- Dispatch revalidates reservations, stock versions, budgets; only then runs sandbox actions.
- Rejection / reservation timeout releases reservations. Material change ⇒ new version ⇒ fresh approvals.
- Partial sandbox handoffs become exceptions; plan → `NEEDS_OPERATOR`.

## Session

```
POST /api/session  {role: "owner"|"operator", shop_id?: int, pin: str}
→ {token, role, shop_id|null, shop_name}
```

## Reference data

```
GET /api/shops → [{id, name, name_hi, owner_name, lat, lng, cash_limit_paise, sharing_opt_in, withdrawn}]
GET /api/products → [{id, brand, name, name_hi, variant, pack_size, unit, category, mrp_paise, emoji, aliases:[str]}]
GET /api/shops/{shop_id}/stock → [{lot_id, product_id, product_name, product_name_hi, emoji, qty, reserved_qty, available_qty,
     retained_floor, cost_paise, expiry_date|null, days_to_expiry|null, condition, permit_share, slow, version}]
GET /api/shops/{shop_id}/needs → [{id, product_id, product_name, qty, urgency: "urgent"|"normal",
     alt_product_ids:[int], budget_paise, min_shelf_days, status}]
GET /api/supplier-quotes?product_id= → [{id, product_id, supplier_name, price_paise, min_order_packs, lead_days}]
```

`paise` = integer Indian paise (₹1 = 100). All money is integer paise everywhere.

## Capture (propose-only; nothing commits until confirm)

```
POST /api/captures  {shop_id, text}   # Hindi, English, code-switched
→ {capture_id, status: "proposed"|"clarification_needed"|"failed",
   proposals: [{kind: "stock_update"|"need", product_id|null, product_name|null, qty|null, unit|null,
                price_ref_paise|null, confidence, ambiguity: null | {reason, candidates:[{product_id, product_name, name_hi, emoji}]},
                question|null}],
   engine: "rules"|"ollama"}
POST /api/captures/audio  (multipart file=)  → same shape, or {status:"failed", engine:"speech", fallback:"manual-form"}
POST /api/captures/invoice (multipart file=) → same shape, or {status:"failed", engine:"ocr", fallback:"manual-form"}
POST /api/captures/{capture_id}/confirm  {edits:[{index, product_id, qty, unit, kind}]}
   header: Idempotency-Key: <uuid>
→ {applied: [{type:"stock_update"|"need", detail}], capture_status:"confirmed"}
```

Rules: ambiguous phrase (e.g. "₹10 wala biscuit" matching 3 SKUs) ⇒ `clarification_needed`, never committed.
Voice/OCR are optional local models; when unavailable they return `failed` with `fallback:"manual-form"` — the UI must show the manual form.

## Inventory & needs (owner-confirmed writes)

```
POST /api/inventory/confirm  {shop_id, changes:[{lot_id?, product_id, qty?, delta?, expiry_date?, condition?, permit_share?, slow?, retained_floor?}], reason}
   header: Idempotency-Key → replays cached response on retry
→ {applied:[...], shop_version}
POST /api/needs  {shop_id, product_id, qty, urgency, alt_product_ids?, budget_paise?, min_shelf_days?}
DELETE /api/needs/{id}
POST /api/supplier-quotes  {product_id, supplier_name, price_paise, min_order_packs?, lead_days?}
```

## Planning

```
POST /api/planning-runs  {case_id: "cluster-main", params?: {time_limit_ms?: 5000, min_shelf_days?: 14, radius_km?: 3.0, include_purchases?: true}}
→ {run_id}
GET  /api/planning-runs/{run_id}
→ {status: "queued"|"running"|"done"|"error", progress: 0-100,
   solver: {status: "OPTIMAL"|"FEASIBLE"|"INFEASIBLE"|"UNKNOWN", objective, time_ms, proven_optimal},
   plan_id|null, why_not: null | {all_purchase: {...}, pairwise_only: {...}, expiry_move_only: {...}}, log: [str]}
```

`solver.status` is reported exactly: a timeout is `UNKNOWN`/`FEASIBLE`, never "infeasible".

```
GET /api/plans/{plan_id} → full decision receipt (shape below)
GET /api/plans/{plan_id}/status → {status, reservations:[...], approvals:[...], sandbox_actions:[...], approvals_missing:[shop_id]}
POST /api/plans/{plan_id}/approve  {}    # owner token, must match participant
POST /api/plans/{plan_id}/reject   {reason}
POST /api/plans/{plan_id}/cancel   {}    # operator only
POST /api/plans/{plan_id}/dispatch {}    # operator only; revalidates then sandbox-executes
```

### Decision receipt shape

```json
{
  "id": 12, "case_id": "cluster-main", "version": 2, "status": "AWAITING_APPROVAL",
  "created_at": "...", "inputs_hash": "ab12...",
  "participants": [1, 2, 3],
  "cycles": [{
     "id": "c1", "shop_path": [1, 3, 2],
     "legs": [{"from_shop": 1, "to_shop": 3, "product_id": 4, "product_name": "Parle-G 100g",
               "emoji": "🍪", "qty": 20, "unit": "pack", "unit_value_paise": 500, "value_paise": 10000,
               "expiry_date": "2026-12-01", "shelf_days": 38}],
     "balancing_paise_by_shop": {"1": -3000, "3": 8000, "2": -5000},
     "transport_paise": 3600, "transport_per_shop_paise": 1200, "slow_packs_redeployed": 20
  }],
  "purchases": [{"shop_id": 2, "product_id": 9, "product_name": "Surf Excel 500g", "qty": 5, "unit_price_paise": 4200, "total_paise": 21000}],
  "coverage": [{"shop_id": 2, "need_id": 31, "product_id": 9, "product_name": "Surf Excel 500g",
                "qty_needed": 15, "qty_covered": 15, "source": "exchange", "urgency": "urgent"}],
  "costs": {"goods_value_exchanged_paise": 46000,
            "balancing_net_by_shop": {"1": -3000, "2": -5000, "3": 8000},
            "purchases_paise": 21000, "transport_paise": 3600, "transaction_fee_paise": 0,
            "cash_out_by_shop": {"1": 3000, "2": 26000, "3": -8000}},
  "assumptions": ["Transport charged at ₹20/km/pack, split evenly", "..."],
  "solver": {"status": "OPTIMAL", "objective": 48012300, "time_ms": 812, "proven_optimal": true},
  "why_not": {"all_purchase": {"coverage_pct": 60, "cash_paise": 92000},
               "pairwise_only": {"coverage_pct": 40, "cash_paise": 41000},
               "expiry_move_only": {"note": "no near-expiry lots matched needs"}},
  "approval_history": [{"shop_id": 1, "decision": "approved", "at": "...", "inputs_hash": "ab12..."}]
}
```

`balancing_paise_by_shop` positive = that shop pays cash, negative = shop is owed (modelled only inside this plan; never netted across plans). `cash_out_by_shop` = what the owner must be able to spend; enforced ≤ cash limit.

## Sandbox (failure rehearsal + simulated execution)

```
POST /api/sandbox/inject {type: "withdraw_shop"|"reduce_stock"|"disconnect", shop_id, product_id?, qty?}
→ {injection_id, effect}
POST /api/sandbox/reset → {ok}
GET  /api/sandbox/state → {injections: [...], withdrawn_shops: [...], disconnected_shops: [...]}
```

Effects: `withdraw_shop` invalidates plans including that shop at revalidation (→ `NEEDS_OPERATOR`, then operator re-plans → new version, fresh approvals). `reduce_stock` breaks reservation revalidation. `disconnect` blocks approvals + loses one sandbox ack (→ partial handoff exception).

## Events / evidence

```
GET /api/cases/{case_id}/events?limit=200 → [{id, ts, actor, event_type, ref_type, ref_id, payload}]
GET /api/cases/{case_id}/export → JSON download (anonymised evidence report)
GET /api/health → {ok, shops, products, open_reservations}
```

Errors: `{detail: string}` with 400/401/403/404/409. 409 = state conflict (e.g. approving a superseded version).
