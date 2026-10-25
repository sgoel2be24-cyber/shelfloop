// Offline outbox: when a capture-confirm fails because the network is down,
// the request body is stashed in localStorage and replayed (same
// Idempotency-Key) on the next `online` event or app load.
import { confirmCaptureRaw } from './client'
import type { CaptureConfirmEdit } from './types'

export const OUTBOX_KEY = 'shelfloop_outbox'

export interface OutboxEntry {
  capture_id: number
  edits: CaptureConfirmEdit[]
  idem_key: string
  queued_at: string
}

function read(): OutboxEntry[] {
  try {
    const raw = localStorage.getItem(OUTBOX_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed as OutboxEntry[]
  } catch {
    return []
  }
}

function write(entries: OutboxEntry[]): void {
  try {
    localStorage.setItem(OUTBOX_KEY, JSON.stringify(entries))
  } catch {
    // storage full / unavailable — nothing sensible to do
  }
}

export function enqueueOutbox(entry: Omit<OutboxEntry, 'queued_at'>): void {
  write([...read(), { ...entry, queued_at: new Date().toISOString() }])
}

export function outboxSize(): number {
  return read().length
}

/**
 * Replay queued capture confirms. Network failures keep the entry (still
 * offline); hard API errors drop the entry so the queue cannot wedge forever.
 * Returns the number of entries successfully flushed.
 */
export async function flushOutbox(): Promise<number> {
  const entries = read()
  if (entries.length === 0) return 0
  const remaining: OutboxEntry[] = []
  let flushed = 0
  for (const entry of entries) {
    try {
      await confirmCaptureRaw(entry.capture_id, entry.edits, entry.idem_key)
      flushed += 1
    } catch (err) {
      if (err instanceof TypeError) {
        // still offline — stop, keep this entry and everything after it
        remaining.push(entry, ...entries.slice(entries.indexOf(entry) + 1))
        break
      }
      // API rejected it (4xx/5xx): drop it, replaying won't help
    }
  }
  write(remaining)
  return flushed
}
