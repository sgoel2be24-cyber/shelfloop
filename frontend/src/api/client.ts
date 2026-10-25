// Typed fetch wrapper for the ShelfLoop API (docs/api-contract.md).
// Dev: same-origin /api via the vite proxy. Built app: absolute base — the
// backend serves dist/ at "/".
import type {
  AuditEvent,
  ClusterSummary,
  ExpiryAction,
  PlanHistoryRow,
  CaptureConfirmEdit,
  CaptureConfirmResponse,
  CaptureResponse,
  HealthResponse,
  InventoryChange,
  InventoryConfirmResponse,
  Lot,
  Need,
  Plan,
  PlanStatusResponse,
  PlanningRun,
  PlanningRunStart,
  Product,
  RunParams,
  SandboxState,
  SessionResponse,
  Shop,
  SupplierQuote,
} from './types'

export const API_BASE: string = import.meta.env.DEV ? '/api' : 'http://localhost:8000/api'

export const TOKEN_KEY = 'shelfloop_token'
export const SESSION_KEY = 'shelfloop_session'

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Raised when the network itself failed after the request was queued offline. */
export class OfflineQueuedError extends Error {
  constructor() {
    super('offline: request queued in outbox')
    this.name = 'OfflineQueuedError'
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(SESSION_KEY)
}

/** crypto.randomUUID needs a secure context; fall back for plain http on LAN. */
export function newIdemKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}-${Math.random().toString(16).slice(2)}`
}

interface RequestOptions {
  method?: string
  body?: unknown
  idemKey?: string
  /** return the raw Response instead of parsing JSON */
  raw?: boolean
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  if (opts.idemKey) headers['Idempotency-Key'] = opts.idemKey

  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: opts.method ?? 'GET',
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    })
  } catch (err) {
    // network failure — let callers decide to queue offline (TypeError from fetch)
    throw err
  }

  if (res.status === 401) {
    clearToken()
    if (!window.location.pathname.startsWith('/login')) {
      window.location.assign('/login')
    }
    throw new ApiError(401, 'unauthorized')
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const j = (await res.json()) as { detail?: unknown }
      if (j && typeof j.detail === 'string') detail = j.detail
    } catch {
      // non-JSON error body
    }
    throw new ApiError(res.status, detail)
  }

  if (opts.raw) return res as unknown as T
  return (await res.json()) as T
}

// ---------- session ----------

export function createSession(role: 'owner' | 'operator', shopId: number | null, pin: string): Promise<SessionResponse> {
  return request<SessionResponse>('/session', {
    method: 'POST',
    body: { role, shop_id: shopId ?? undefined, pin },
  })
}

// ---------- reference data ----------

export const listShops = () => request<Shop[]>('/shops')
export const listProducts = () => request<Product[]>('/products')
export const getStock = (shopId: number) => request<Lot[]>(`/shops/${shopId}/stock`)
export const getNeeds = (shopId: number) => request<Need[]>(`/shops/${shopId}/needs`)
export const getSupplierQuotes = (productId: number) =>
  request<SupplierQuote[]>(`/supplier-quotes?product_id=${productId}`)

// ---------- capture ----------

export function createCapture(shopId: number, text: string): Promise<CaptureResponse> {
  return request<CaptureResponse>('/captures', { method: 'POST', body: { shop_id: shopId, text } })
}

export function confirmCaptureRaw(
  captureId: number,
  edits: CaptureConfirmEdit[],
  idemKey: string,
): Promise<CaptureConfirmResponse> {
  return request<CaptureConfirmResponse>(`/captures/${captureId}/confirm`, {
    method: 'POST',
    body: { edits },
    idemKey,
  })
}

// ---------- inventory & needs ----------

export function inventoryConfirm(
  shopId: number,
  changes: InventoryChange[],
  reason: string,
): Promise<InventoryConfirmResponse> {
  return request<InventoryConfirmResponse>('/inventory/confirm', {
    method: 'POST',
    body: { shop_id: shopId, changes, reason },
    idemKey: newIdemKey(),
  })
}

export function createNeed(
  shopId: number,
  body: { product_id: number; qty: number; urgency: 'urgent' | 'normal'; alt_product_ids?: number[]; budget_paise?: number; min_shelf_days?: number },
): Promise<Need> {
  return request<Need>('/needs', { method: 'POST', body: { shop_id: shopId, ...body } })
}

export const deleteNeed = (needId: number) => request<unknown>(`/needs/${needId}`, { method: 'DELETE' })

export function addSupplierQuote(body: {
  product_id: number
  supplier_name: string
  price_paise: number
  min_order_packs?: number
  lead_days?: number
}): Promise<SupplierQuote> {
  return request<SupplierQuote>('/supplier-quotes', { method: 'POST', body })
}

// ---------- planning ----------

export function startPlanningRun(params: RunParams): Promise<PlanningRunStart> {
  return request<PlanningRunStart>('/planning-runs', {
    method: 'POST',
    body: { case_id: 'cluster-main', params },
  })
}

export const getPlanningRun = (runId: number) => request<PlanningRun>(`/planning-runs/${runId}`)
export const getPlan = (planId: number) => request<Plan>(`/plans/${planId}`)
export const getPlanStatus = (planId: number) => request<PlanStatusResponse>(`/plans/${planId}/status`)

export const approvePlan = (planId: number) =>
  request<unknown>(`/plans/${planId}/approve`, { method: 'POST', body: {} })

export const rejectPlan = (planId: number, reason: string) =>
  request<unknown>(`/plans/${planId}/reject`, { method: 'POST', body: { reason } })

export const submitPlan = (planId: number) =>
  request<{ plan_id: number; status: string; reservations_expire_at: string }>(
    `/plans/${planId}/submit`, { method: 'POST', body: {} })

export const cancelPlan = (planId: number) =>
  request<unknown>(`/plans/${planId}/cancel`, { method: 'POST', body: {} })

export const dispatchPlan = (planId: number) =>
  request<unknown>(`/plans/${planId}/dispatch`, { method: 'POST', body: {} })

// ---------- sandbox ----------

export function sandboxInject(body: {
  type: 'withdraw_shop' | 'reduce_stock' | 'disconnect'
  shop_id: number
  product_id?: number
  qty?: number
}): Promise<{ injection_id: number | string; effect: string }> {
  return request('/sandbox/inject', { method: 'POST', body })
}

export const sandboxReset = () => request<{ ok: boolean }>('/sandbox/reset', { method: 'POST' })
export const sandboxState = () => request<SandboxState>('/sandbox/state')

// ---------- cluster analytics ----------
export const getClusterSummary = (caseId: string) =>
  request<ClusterSummary>(`/cases/${caseId}/summary`)
export const getExpiryActions = (shopId: number, withinDays = 60) =>
  request<ExpiryAction[]>(`/shops/${shopId}/expiry-actions?within_days=${withinDays}`)
export interface DirectoryRow extends Shop {
  lots: number
  packs: number
  stock_value_paise: number
  near_expiry_lots: number
  slow_packs: number
  open_needs: number
  need_packs: number
}
export interface ShopPulse {
  lots: number
  packs: number
  stock_value_paise: number
  near_expiry_value_paise: number
  slow_packs: number
  open_needs: number
  need_packs: number
  reserved_packs: number
}
export const getCaseDirectory = (caseId: string) =>
  request<DirectoryRow[]>(`/cases/${caseId}/directory`)
export const getShopPulse = (shopId: number) =>
  request<ShopPulse>(`/shops/${shopId}/pulse`)
export const getPlanHistory = (caseId: string, limit = 30) =>
  request<PlanHistoryRow[]>(`/cases/${caseId}/plans?limit=${limit}`)

// ---------- events / evidence ----------

export const getEvents = (caseId: string, limit = 200) =>
  request<AuditEvent[]>(`/cases/${caseId}/events?limit=${limit}`)

export const getHealth = () => request<HealthResponse>('/health')

export async function downloadExport(): Promise<void> {
  const res = await request<Response>('/cases/cluster-main/export', { raw: true })
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `shelfloop-evidence-cluster-main-${new Date().toISOString().slice(0, 10)}.json`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
