import { useEffect, useMemo, useState } from 'react'
import { ApiError, approvePlan, getPlanStatus, rejectPlan } from '../../api/client'
import { fetchOwnerPlans, filterAwaitingMyApproval } from '../../api/discovery'
import type { Plan, PlanStatusResponse } from '../../api/types'
import { Countdown } from '../../components/Countdown'
import { PlanReceipt } from '../../components/PlanReceipt'
import { useI18n } from '../../i18n'
import { useAsyncData } from '../../lib/useAsyncData'
import { useSession } from '../../state/Session'
import { useToast } from '../../state/Toast'

export default function Approvals() {
  const { t } = useI18n()
  const { session } = useSession()
  const shopId = session!.shopId!

  const { data: plans, error, loading, reload } = useAsyncData(() => fetchOwnerPlans(shopId), [shopId])
  const awaiting = useMemo(() => filterAwaitingMyApproval(plans ?? [], shopId), [plans, shopId])

  const [statuses, setStatuses] = useState<Record<number, PlanStatusResponse | null>>({})
  useEffect(() => {
    let alive = true
    void Promise.all(
      awaiting.map((p) =>
        getPlanStatus(p.id)
          .then((s) => [p.id, s] as const)
          .catch(() => [p.id, null] as const),
      ),
    ).then((entries) => {
      if (alive) setStatuses(Object.fromEntries(entries))
    })
    return () => {
      alive = false
    }
  }, [awaiting])

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-extrabold text-brand">{t('appr.title')}</h1>
        <p className="text-sm text-ink/60">{t('appr.subtitle')}</p>
      </header>

      {loading && <p className="text-sm text-ink/60">{t('common.loading')}</p>}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {t('common.error')} — {error}
          <button type="button" className="ml-2 font-bold underline" onClick={reload}>
            {t('common.retry')}
          </button>
        </div>
      )}
      {!loading && !error && awaiting.length === 0 && <div className="card p-5 text-sm text-ink/70">{t('appr.empty')}</div>}

      {awaiting.map((plan) => (
        <ApprovalCard key={`${plan.id}-${plan.version}`} plan={plan} status={statuses[plan.id] ?? null} onDone={reload} />
      ))}
    </div>
  )
}

function ApprovalCard({
  plan,
  status,
  onDone,
}: {
  plan: Plan
  status: PlanStatusResponse | null
  onDone: () => void
}) {
  const { t } = useI18n()
  const { push } = useToast()
  const [seen, setSeen] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const expiresAt = useMemo(() => {
    const times = (status?.reservations ?? [])
      .map((r) => r.expires_at)
      .filter((x): x is string => typeof x === 'string')
      .map((x) => Date.parse(x))
      .filter((n) => !Number.isNaN(n))
    if (times.length === 0) return null
    return new Date(Math.min(...times)).toISOString()
  }, [status])

  function fail(err: unknown) {
    if (err instanceof ApiError && err.status === 403) push(t('toast.forbidden'), 'err')
    else if (err instanceof ApiError && err.status === 409) push(t('toast.conflict'), 'err')
    else if (err instanceof TypeError) push(t('toast.network'), 'err')
    else push(err instanceof Error ? err.message : t('common.error'), 'err')
  }

  async function doApprove() {
    if (!seen) {
      push(t('appr.needSeen'), 'err')
      return
    }
    setBusy(true)
    try {
      await approvePlan(plan.id)
      push(t('toast.approved'))
      onDone()
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  async function doReject() {
    if (!reason.trim()) {
      push(t('toast.reasonRequired'), 'err')
      return
    }
    setBusy(true)
    try {
      await rejectPlan(plan.id, reason.trim())
      push(t('toast.rejected'))
      onDone()
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-3">
      {expiresAt && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-accent/40 bg-accent/10 px-4 py-3">
          <span className="text-lg" aria-hidden>
            ⏳
          </span>
          <span className="font-bold text-ink">{t('appr.expires')}</span>
          <Countdown expiresAt={expiresAt} className="text-xl" />
        </div>
      )}

      <PlanReceipt plan={plan} />

      <div className="card p-4">
        <label className="flex items-start gap-3 text-sm font-semibold text-ink">
          <input type="checkbox" className="mt-0.5 h-5 w-5" checked={seen} onChange={(e) => setSeen(e.target.checked)} />
          {t('appr.seen')}
        </label>

        {rejecting ? (
          <div className="mt-3 space-y-2">
            <label className="label" htmlFor={`reject-reason-${plan.id}`}>
              {t('appr.reason')}
            </label>
            <input
              id={`reject-reason-${plan.id}`}
              className="field"
              value={reason}
              placeholder={t('appr.reasonPlaceholder')}
              onChange={(e) => setReason(e.target.value)}
            />
            <div className="flex gap-2">
              <button type="button" className="btn-danger flex-1" disabled={busy || !reason.trim()} onClick={() => void doReject()}>
                {t('today.reject')}
              </button>
              <button type="button" className="btn-ghost flex-1" onClick={() => setRejecting(false)}>
                {t('common.cancel')}
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-3 flex gap-2">
            <button type="button" className="btn-accent flex-1" disabled={busy || !seen} onClick={() => void doApprove()}>
              {t('today.approve')}
            </button>
            <button type="button" className="btn-ghost flex-1" disabled={busy} onClick={() => setRejecting(true)}>
              {t('today.reject')}
            </button>
          </div>
        )}
        {!seen && !rejecting && <p className="mt-2 text-xs text-ink/50">{t('appr.needSeen')}</p>}
      </div>
    </section>
  )
}
