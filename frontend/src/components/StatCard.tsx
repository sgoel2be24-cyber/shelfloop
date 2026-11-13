import type { ReactNode } from 'react'
import { Icon, type IconName } from './Icon'

/** KPI tile with icon, value, trend line and an optional accent tone. */
export function StatCard({
  icon,
  label,
  value,
  sub,
  tone = 'default',
}: {
  icon: string
  label: string
  value: ReactNode
  sub?: ReactNode
  tone?: 'default' | 'accent' | 'warn' | 'good'
}) {
  const tones: Record<string, string> = {
    default: 'border-ink/10 bg-white',
    accent: 'border-accent/30 bg-accent/5',
    warn: 'border-amber-300 bg-amber-50',
    good: 'border-green-300 bg-green-50',
  }
  return (
    <div className={`metric-card ${tones[tone]}`}>
      <div className="flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-wider text-ink/60">
        {label}
        <span className="metric-icon" aria-hidden>
          {['home', 'box', 'clock', 'ledger'].includes(icon) ? <Icon name={icon as IconName} size={16} /> : icon}
        </span>
      </div>
      <div className="metric-value tabular">{value}</div>
      {sub && <div className="mt-2 text-[11px] text-ink/55">{sub}</div>}
    </div>
  )
}

/** Shimmering skeleton block for loading states. */
export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`sl-skeleton rounded-lg ${className}`} />
}

/** Horizontal bar chart (pure divs) for category/series data. */
export function BarList({
  items,
  formatValue,
}: {
  items: { label: string; value: number; color?: string }[]
  formatValue?: (v: number) => string
}) {
  const max = Math.max(1, ...items.map((i) => i.value))
  return (
    <div className="space-y-2">
      {items.map((it) => (
        <div key={it.label} className="flex items-center gap-2 text-sm">
          <span className="w-24 shrink-0 truncate capitalize text-ink/70">{it.label}</span>
          <div className="h-4 flex-1 overflow-hidden rounded-full bg-ink/5">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${(100 * it.value) / max}%`, background: it.color ?? '#799A69' }}
            />
          </div>
          <span className="w-20 shrink-0 text-right text-xs font-bold tabular text-ink/70">
            {formatValue ? formatValue(it.value) : it.value}
          </span>
        </div>
      ))}
    </div>
  )
}

/** SVG donut for a single percentage. */
export function CoverageDonut({ pct, label }: { pct: number; label?: string }) {
  const r = 42
  const c = 2 * Math.PI * r
  const filled = (Math.max(0, Math.min(100, pct)) / 100) * c
  const color = pct >= 70 ? '#16A34A' : pct >= 40 ? '#E8702A' : '#DC2626'
  return (
    <div className="relative inline-flex h-28 w-28 items-center justify-center">
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
        <circle cx="50" cy="50" r={r} fill="none" stroke="#1F243014" strokeWidth="12" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${c - filled}`}
          className="transition-all duration-700"
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-xl font-extrabold tabular text-ink">{Math.round(pct)}%</div>
        {label && <div className="text-[10px] font-semibold uppercase text-ink/50">{label}</div>}
      </div>
    </div>
  )
}

/** Cash comparison bars for the "why not" block. Lower = better. */
export function WhyNotBars({
  rows,
}: {
  rows: { label: string; cashPaise: number; coveragePct: number; highlight?: boolean }[]
}) {
  const max = Math.max(1, ...rows.map((r) => r.cashPaise))
  return (
    <div className="space-y-3">
      {rows.map((r) => (
        <div key={r.label}>
          <div className="mb-1 flex justify-between text-xs font-semibold">
            <span className={r.highlight ? 'text-brand' : 'text-ink/60'}>{r.label}</span>
            <span className="tabular text-ink/70">
              {r.coveragePct}% · ₹{(r.cashPaise / 100).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
            </span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-ink/5">
            <div
              className={`h-full rounded-full ${r.highlight ? 'bg-gradient-to-r from-accent to-brand' : 'bg-ink/25'}`}
              style={{ width: `${(100 * r.cashPaise) / max}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
