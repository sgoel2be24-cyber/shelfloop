// Plan discovery for shop owners.
//
// The API contract (v1) defines GET /api/plans/{id} but no "list plans for
// shop" endpoint, so discovery tries, in order:
//   1. GET /api/shops/{id}/plans            (most natural REST extension)
//   2. GET /api/plans?shop_id={id}          (filter-style extension)
//   3. GET /api/cases/cluster-main/events   (audit events -> plan ids)
// The first one that answers wins. If none do, the UI shows an honest empty
// state ("no plan for your shop yet").
import { ApiError, getEvents, getPlan, request } from './client'
import type { Plan } from './types'

const CASE_ID = 'cluster-main'
const DISCOVERY_STATUSES = [404, 405, 400, 501]

function isMissingEndpoint(err: unknown): boolean {
  return err instanceof ApiError && DISCOVERY_STATUSES.includes(err.status)
}

function normalizePlanList(raw: unknown): Plan[] {
  if (Array.isArray(raw)) {
    // either Plan[] or a list of plan ids
    if (raw.length > 0 && typeof raw[0] === 'object' && raw[0] !== null) return raw as Plan[]
    return []
  }
  if (raw && typeof raw === 'object') {
    const obj = raw as { plans?: unknown }
    if (Array.isArray(obj.plans)) return obj.plans as Plan[]
  }
  return []
}

async function fetchEachPlan(ids: number[]): Promise<Plan[]> {
  const capped = ids.slice(-10) // most recent ones; audit events arrive oldest-first
  const plans = await Promise.all(capped.map((id) => getPlan(id).catch(() => null)))
  return plans.filter((p): p is Plan => p !== null)
}

export async function fetchOwnerPlans(shopId: number): Promise<Plan[]> {
  // 1) dedicated per-shop endpoint
  try {
    const raw = await request<unknown>(`/shops/${shopId}/plans`)
    return normalizePlanList(raw)
  } catch (err) {
    if (!isMissingEndpoint(err)) throw err
  }

  // 2) collection endpoint with shop filter
  try {
    const raw = await request<unknown>(`/plans?shop_id=${shopId}`)
    return normalizePlanList(raw)
  } catch (err) {
    if (!isMissingEndpoint(err)) throw err
  }

  // 3) audit-event scan: plan events carry ref_type "plan" + ref_id
  const events = await getEvents(CASE_ID, 200)
  const planIds: number[] = []
  for (const ev of events) {
    if (typeof ev.ref_id === 'number' && String(ev.ref_type).toLowerCase().includes('plan')) {
      if (!planIds.includes(ev.ref_id)) planIds.push(ev.ref_id)
    }
  }
  const plans = await fetchEachPlan(planIds)
  return plans.filter((p) => Array.isArray(p.participants) && p.participants.includes(shopId))
}

/** Plans where this shop still has a decision to make. */
export function filterAwaitingMyApproval(plans: Plan[], shopId: number): Plan[] {
  return plans
    .filter((p) => p.status === 'AWAITING_APPROVAL')
    .filter((p) => !(p.approval_history ?? []).some((a) => a.shop_id === shopId && a.decision === 'approved'))
    .sort(
      (a, b) =>
        (b.version ?? 0) - (a.version ?? 0) || String(b.created_at).localeCompare(String(a.created_at)),
    )
}

/** Latest plan that covers this shop and is still meaningful for "Today". */
export function pickLatestPlan(plans: Plan[], shopId: number): Plan | null {
  const alive = plans
    .filter((p) => Array.isArray(p.participants) && p.participants.includes(shopId))
    .filter((p) => !['REJECTED', 'EXPIRED', 'CANCELLED'].includes(String(p.status)))
    .sort(
      (a, b) =>
        (b.version ?? 0) - (a.version ?? 0) || String(b.created_at).localeCompare(String(a.created_at)),
    )
  return alive[0] ?? null
}
