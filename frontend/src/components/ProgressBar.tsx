/** Thin indigo progress bar, 0-100. */
export function ProgressBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(value)))
  return (
    <div className="h-3 w-full overflow-hidden rounded-full bg-ink/10" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full rounded-full bg-brand transition-all duration-500" style={{ width: `${pct}%` }} />
    </div>
  )
}
