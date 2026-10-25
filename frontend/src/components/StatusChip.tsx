import { useI18n } from '../i18n'
import type { TKey } from '../i18n'

const STATUS_KEYS: Record<string, TKey> = {
  PROPOSED: 'st.PROPOSED',
  AWAITING_APPROVAL: 'st.AWAITING_APPROVAL',
  APPROVED: 'st.APPROVED',
  SANDBOX_DISPATCHED: 'st.SANDBOX_DISPATCHED',
  COMPLETED: 'st.COMPLETED',
  REJECTED: 'st.REJECTED',
  EXPIRED: 'st.EXPIRED',
  CANCELLED: 'st.CANCELLED',
  NEEDS_OPERATOR: 'st.NEEDS_OPERATOR',
  queued: 'st.queued',
  running: 'st.running',
  done: 'st.done',
  error: 'st.error',
}

const STATUS_STYLES: Record<string, string> = {
  PROPOSED: 'text-ink/70 bg-ink/5',
  AWAITING_APPROVAL: 'text-amber-700 bg-amber-50',
  APPROVED: 'text-green-700 bg-green-50',
  SANDBOX_DISPATCHED: 'text-brand bg-brand/5',
  COMPLETED: 'text-green-700 bg-green-50',
  REJECTED: 'text-red-600 bg-red-50',
  EXPIRED: 'text-ink/50 bg-ink/5',
  CANCELLED: 'text-ink/50 bg-ink/5',
  NEEDS_OPERATOR: 'text-red-600 bg-red-50',
}

/** Plan / run status chip with bilingual label; unknown statuses fall back to raw. */
export function StatusChip({ status }: { status: string }) {
  const { t } = useI18n()
  const key = STATUS_KEYS[status]
  return (
    <span className={`stamp ${STATUS_STYLES[status] ?? 'bg-ink/5 text-ink/70'}`}>
      {key ? t(key) : status}
    </span>
  )
}
