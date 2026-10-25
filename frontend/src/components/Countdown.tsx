import { useEffect, useState } from 'react'
import { useI18n } from '../i18n'

/** Re-render on an interval; used by Countdown and speech summaries. */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(timer)
  }, [intervalMs])
  return now
}

function fmt(msLeft: number): string {
  const totalSec = Math.max(0, Math.floor(msLeft / 1000))
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

/** mm:ss string for a millisecond remainder (for speech + text templates). */
export function formatMsLeft(msLeft: number): string {
  return fmt(msLeft)
}

/** Live mm:ss countdown to an ISO timestamp; turns red under 2 minutes. */
export function Countdown({ expiresAt, className }: { expiresAt: string | null; className?: string }) {
  const { t } = useI18n()
  const now = useNow(1000)

  if (!expiresAt) return null
  const target = Date.parse(expiresAt)
  if (Number.isNaN(target)) return null

  const diff = target - now
  if (diff <= 0) {
    return <span className={`tabular font-bold text-red-600 ${className ?? ''}`}>{t('appr.expired')}</span>
  }
  const urgent = diff <= 2 * 60 * 1000
  return (
    <span className={`tabular font-bold ${urgent ? 'text-red-600' : 'text-brand'} ${className ?? ''}`}>
      {fmt(diff)}
    </span>
  )
}
