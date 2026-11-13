// Shapes straight from docs/api-contract.md (v1). Code against these exactly.

export type Role = 'owner' | 'operator'

export type PlanStatus =
  | 'PROPOSED'
  | 'AWAITING_APPROVAL'
  | 'APPROVED'
  | 'SANDBOX_DISPATCHED'
  | 'COMPLETED'
  | 'REJECTED'
  | 'EXPIRED'
  | 'CANCELLED'
  | 'NEEDS_OPERATOR'

export type SolverStatus = 'OPTIMAL' | 'FEASIBLE' | 'INFEASIBLE' | 'UNKNOWN'

export interface SessionResponse {
  token: string
  role: Role
  shop_id: number | null
  shop_name: string
}

export interface Shop {
  id: number
  name: string
  name_hi: string
  owner_name: string
  lat: number
  lng: number
  cash_limit_paise: number
  sharing_opt_in: boolean
  withdrawn: boolean
  version: number
}

export interface Product {
  id: number
  brand: string
  name: string
  name_hi: string
  variant: string
  pack_size: string
  unit: string
  category: string
  mrp_paise: number
  emoji: string
  aliases: string[]
}

export interface Lot {
  lot_id: number
  product_id: number
  product_name: string
  product_name_hi: string
  emoji: string
  qty: number
  reserved_qty: number
  available_qty: number
  retained_floor: number
  cost_paise: number
  expiry_date: string | null
  days_to_expiry: number | null
  condition: string
  permit_share: boolean
  slow: boolean
  version: number
}

export interface Need {
  id: number
  product_id: number
  product_name: string
  qty: number
  urgency: 'urgent' | 'normal'
  alt_product_ids: number[]
  budget_paise: number | null
  min_shelf_days: number | null
  status: string
}

export interface SupplierQuote {
  id: number
  product_id: number
  supplier_name: string
  price_paise: number
  min_order_packs: number
  lead_days: number
}

// ---------- capture ----------

export type CaptureStatus = 'proposed' | 'clarification_needed' | 'failed'

export interface CaptureCandidate {
  product_id: number
  product_name: string
  name_hi: string
  emoji: string
}

export interface CaptureAmbiguity {
  reason: string
  candidates: CaptureCandidate[]
}

export interface CaptureProposal {
  kind: 'stock_update' | 'need'
  product_id: number | null
  product_name: string | null
  qty: number | null
  unit: string | null
  price_ref_paise: number | null
  confidence: number
  ambiguity: CaptureAmbiguity | null
  question: string | null
}

export interface CaptureResponse {
  capture_id: number | null
  warnings?: string[]
  questions?: string[]
  fallback?: string
  status: CaptureStatus
  proposals: CaptureProposal[]
  engine: string
}

export interface CaptureConfirmEdit {
  index: number
  product_id: number
  qty: number
  unit: string
  kind: string
}

export interface CaptureConfirmResponse {
  applied: { type: string; detail: string }[]
  capture_status: string
}

export interface InventoryChange {
  lot_id?: number
  product_id: number
  qty?: number
  delta?: number
  expiry_date?: string
  condition?: string
  permit_share?: boolean
  slow?: boolean
  retained_floor?: number
  expected_version?: number
  cost_paise?: number
}

export interface InventoryConfirmResponse {
  applied: { type: string; detail: string }[]
  shop_version: number
}

// ---------- planning ----------

export interface RunParams {
  shop_ids?: number[]
  time_limit_ms?: number
  min_shelf_days?: number
  radius_km?: number
  include_purchases?: boolean
}

export interface PlanningRunStart {
  run_id: number
}

export interface SolverInfo {
  status: SolverStatus
  objective: number
  time_ms: number
  proven_optimal: boolean
}

export interface WhyNotOption {
  coverage_pct?: number
  cash_paise?: number
  note?: string
}

export interface WhyNot {
  all_purchase?: WhyNotOption
  pairwise_only?: WhyNotOption
  expiry_move_only?: WhyNotOption
}

export interface PlanningRun {
  status: 'queued' | 'running' | 'done' | 'error'
  progress: number
  solver: SolverInfo | null
  plan_id: number | null
  why_not: WhyNot | null
  log: string[]
}

// ---------- decision receipt ----------

export interface PlanLeg {
  from_shop: number
  to_shop: number
  product_id: number
  product_name: string
  emoji: string
  qty: number
  unit: string
  unit_value_paise: number
  value_paise: number
  expiry_date: string | null
  shelf_days: number | null
}

export interface PlanCycle {
  id: string
  shop_path: number[]
  legs: PlanLeg[]
  balancing_paise_by_shop: Record<string, number>
  transport_paise: number
  transport_by_shop_paise?: Record<string, number>
  transport_per_shop_paise: number
  slow_packs_redeployed: number
}

export interface PlanPurchase {
  shop_id: number
  product_id: number
  product_name: string
  qty: number
  unit_price_paise: number
  total_paise: number
}

export interface PlanCoverage {
  shop_id: number
  need_id: number
  product_id: number
  product_name: string
  qty_needed: number
  qty_covered: number
  source: string
  urgency: string
}

export interface PlanCosts {
  goods_value_exchanged_paise: number
  balancing_net_by_shop: Record<string, number>
  purchases_paise: number
  transport_paise: number
  transaction_fee_paise: number
  cash_out_by_shop: Record<string, number>
}

export interface ApprovalEvent {
  shop_id: number
  decision: string
  at: string
  inputs_hash: string
}

export interface Plan {
  id: number
  case_id: string
  version: number
  status: PlanStatus | string
  created_at: string
  inputs_hash: string
  participants: number[]
  cycles: PlanCycle[]
  purchases: PlanPurchase[]
  coverage: PlanCoverage[]
  costs: PlanCosts
  assumptions: string[]
  solver: SolverInfo
  why_not: WhyNot | null
  approval_history: ApprovalEvent[]
}

// plan status item shapes for reservations/sandbox_actions are elided in the
// contract ("[...]"); keep permissive but known-optional fields typed.
export interface ReservationInfo {
  id?: number
  plan_id?: number
  shop_id?: number
  lot_id?: number
  qty?: number
  expires_at?: string | null
  [key: string]: unknown
}

export interface SandboxActionInfo {
  id?: number | string
  type?: string
  kind?: string
  action?: string
  shop_id?: number
  product_id?: number
  lot_id?: number
  qty?: number
  status?: string
  ack?: boolean | string
  acked?: boolean
  acknowledged?: boolean
  [key: string]: unknown
}

export interface PlanStatusResponse {
  status: PlanStatus | string
  reservations: ReservationInfo[]
  approvals: ApprovalEvent[]
  sandbox_actions: SandboxActionInfo[]
  approvals_missing: number[]
}

// ---------- sandbox ----------

export interface InjectionResponse {
  injection_id: number | string
  effect: string
}

export interface InjectionRecord {
  id?: number | string
  injection_id?: number | string
  type?: string
  shop_id?: number
  product_id?: number
  qty?: number
  ts?: string
  [key: string]: unknown
}

export interface SandboxState {
  injections: InjectionRecord[]
  withdrawn_shops: number[]
  disconnected_shops: number[]
}

// ---------- events / evidence ----------

export interface AuditEvent {
  id: number
  ts: string
  actor: string
  event_type: string
  ref_type: string
  ref_id: number
  payload: unknown
}

export interface HealthResponse {
  ok: boolean
  shops: number
  products: number
  open_reservations: number
}


// ---------- cluster analytics ----------

export interface ClusterSummary {
  shops: number
  sharing_on: number
  stock_packs: number
  stock_value_paise: number
  near_expiry_14_value_paise: number
  near_expiry_30_value_paise: number
  slow_packs: number
  slow_value_paise: number
  open_needs: number
  open_need_packs: number
  urgent_packs: number
  active_reservations: number
  last_plan: {
    id: number
    version: number
    status: string
    solver_status: string
    cycles: number
    purchases: number
    coverage_pct: number
    cash_out_paise: number
    slow_packs: number
  } | null
  top_categories: { category: string; value_paise: number }[]
}

export interface ExpiryAction {
  lot_id: number
  product_id: number
  product_name: string
  product_name_hi: string
  emoji: string
  qty: number
  expiry_date: string
  days_left: number
  value_paise: number
  matched_need_packs: number
  suggestion: 'exchange' | 'return_to_distributor' | 'use_first'
  note: string
}

export interface PlanHistoryRow {
  id: number
  version: number
  status: PlanStatus
  created_at: string
  supersedes_id: number | null
  inputs_hash: string
  solver_status: string
  cycles: number
  purchases: number
  coverage_pct: number
  cash_out_paise: number
  slow_packs: number
}
