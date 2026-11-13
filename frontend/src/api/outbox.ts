// Durable, owner-scoped confirmations. Failed entries remain visible for review.
import { ApiError, confirmCaptureRaw, SESSION_KEY } from './client'
import type { CaptureConfirmEdit } from './types'

export const OUTBOX_KEY = 'shelfloop_outbox'
export interface OutboxEntry {
  capture_id: number
  edits: CaptureConfirmEdit[]
  idem_key: string
  shop_id: number
  queued_at: string
  error?: string
}
function currentShop(): number | null {
  try {
    const session = JSON.parse(sessionStorage.getItem(SESSION_KEY) ?? 'null')
    return session?.role === 'owner' && Number.isInteger(session.shop_id) ? session.shop_id : null
  } catch { return null }
}
function read(): OutboxEntry[] {
  try { const rows: unknown = JSON.parse(localStorage.getItem(OUTBOX_KEY) ?? '[]'); return Array.isArray(rows) ? rows : [] }
  catch { return [] }
}
function write(rows: OutboxEntry[]): void {
  localStorage.setItem(OUTBOX_KEY, JSON.stringify(rows))
  window.dispatchEvent(new Event('shelfloop-outbox'))
}
export function getOutboxEntries(): OutboxEntry[] { return read().filter(e => e.shop_id === currentShop()) }
export function enqueueOutbox(entry: Omit<OutboxEntry, 'queued_at'|'shop_id'>): void {
  const shop = currentShop()
  if (shop === null) throw new Error('Sign in as the shop owner before saving a confirmation.')
  const rows = read()
  if (!rows.some(e => e.idem_key === entry.idem_key && e.shop_id === shop))
    write([...rows, { ...entry, shop_id: shop, queued_at: new Date().toISOString() }])
}
export function outboxSize(): number { return getOutboxEntries().length }
let flushing: Promise<number> | null = null
export function flushOutbox(): Promise<number> {
  if (flushing) return flushing
  flushing = replay().finally(() => { flushing = null })
  return flushing
}
async function replay(): Promise<number> {
  const shop = currentShop()
  if (shop === null) return 0
  let count = 0
  for (const entry of getOutboxEntries()) {
    if (currentShop() !== shop) break
    try {
      await confirmCaptureRaw(entry.capture_id, entry.edits, entry.idem_key)
      write(read().filter(e => !(e.shop_id === shop && e.idem_key === entry.idem_key)))
      count++
    } catch (err) {
      if (err instanceof TypeError || (err instanceof ApiError && (err.status >= 500 || err.status === 429))) break
      write(read().map(e => e.shop_id === shop && e.idem_key === entry.idem_key
        ? { ...e, error: err instanceof Error ? err.message : 'Confirmation needs review' } : e))
      if (err instanceof ApiError && err.status === 401) break
    }
  }
  return count
}
