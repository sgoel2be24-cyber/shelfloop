import type { SolverStatus } from '../api/types'

const STYLES: Record<SolverStatus, string> = {
  OPTIMAL: 'bg-green-100 text-green-800',
  FEASIBLE: 'bg-amber-100 text-amber-800',
  INFEASIBLE: 'bg-red-100 text-red-700',
  UNKNOWN: 'bg-ink/10 text-ink',
}

/** Solver badge: reported exactly as the API gives it (OPTIMAL / FEASIBLE / …). */
export function SolverBadge({ status, provenOptimal }: { status: SolverStatus; provenOptimal?: boolean }) {
  return (
    <span className={`chip ${STYLES[status]}`} title={provenOptimal ? 'proven optimal' : undefined}>
      {status}
      {provenOptimal ? ' ✓' : ''}
    </span>
  )
}
