import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, cancelPlan, dispatchPlan, getPlan, getPlanHistory, getPlanningRun, startPlanningRun, submitPlan } from '../../api/client'
import { useAsyncData } from '../../lib/useAsyncData'
import type { PlanningRun, SandboxActionInfo, SolverStatus } from '../../api/types'
import { ProgressBar } from '../../components/ProgressBar'
import { PlanReceipt } from '../../components/PlanReceipt'
import { SolverBadge } from '../../components/SolverBadge'
import { StatusChip } from '../../components/StatusChip'
import { useI18n } from '../../i18n'
import { fetchShops, shopLabel } from '../../lib/data'
import { formatNumber } from '../../lib/format'
import { useToast } from '../../state/Toast'
import { useOperator } from './OperatorShell'

function ackOf(a: SandboxActionInfo): boolean | null {
  if (typeof a.ack === 'boolean') return a.ack
  if (typeof a.acked === 'boolean') return a.acked
  if (typeof a.acknowledged === 'boolean') return a.acknowledged
  if (typeof a.status === 'string') return /ack/i.test(a.status)
  return null
}

function labelOf(a: SandboxActionInfo): string {
  const kind = a.type ?? a.kind ?? a.action
  if (typeof kind === 'string' && kind) return kind
  const rest = { ...a }
  delete rest.id
  return JSON.stringify(rest)
}

export default function Planning() {
  const { t, lang } = useI18n()
  const { push } = useToast()
  const op = useOperator()
  const history = useAsyncData(() => getPlanHistory('cluster-main'), [op.plan?.id, op.plan?.status])
  const { data: shops } = useAsyncData(() => fetchShops(), [])

  const [runId, setRunId] = useState<number | null>(null)
  const [run, setRun] = useState<PlanningRun | null>(null)
  const [starting, setStarting] = useState(false)
  const [dispatching, setDispatching] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const pollErrors = useRef(0)

  // params
  const [timeLimitS, setTimeLimitS] = useState('5')
  const [minShelf, setMinShelf] = useState('14')
  const [radius, setRadius] = useState('3')
  const [includePurchases, setIncludePurchases] = useState(true)
  const [urgentOnly, setUrgentOnly] = useState(false)
  const [demoOnly, setDemoOnly] = useState(true)

  const name = (id: number) => shopLabel(shops?.find((s) => s.id === id), id, lang)

  const startRun = useCallback(
    async (params?: { time_limit_ms?: number; min_shelf_days?: number; radius_km?: number; include_purchases?: boolean }) => {
      const p = {
        time_limit_ms: Math.max(500, Math.floor((Number(timeLimitS) || 5) * 1000)),
        min_shelf_days: Math.max(0, Math.floor(Number(minShelf) || 0)),
        radius_km: Number(radius) > 0 ? Number(radius) : 3.0,
        include_purchases: includePurchases,
        urgent_only: urgentOnly,
        shop_ids: demoOnly ? [1, 2, 3] : undefined,
        ...(params ?? {}),
      }
      op.setLastParams(p)
      setStarting(true)
      setRun(null)
      try {
        const { run_id } = await startPlanningRun(p)
        setRunId(run_id)
      } catch (err) {
        push(err instanceof ApiError ? err.message : t('op.runFailed'), 'err')
      } finally {
        setStarting(false)
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [timeLimitS, minShelf, radius, includePurchases, urgentOnly, demoOnly, op.setLastParams, push, t],
  )

  // poll the run every 1s until done/error
  useEffect(() => {
    if (runId == null) return
    let alive = true
    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const r = await getPlanningRun(runId)
          pollErrors.current = 0
          if (!alive) return
          setRun(r)
          if (r.status === 'done' || r.status === 'error') {
            window.clearInterval(timer)
            setRunId(null)
            if (r.status === 'done' && r.plan_id != null) {
              try {
                const plan = await getPlan(r.plan_id)
                op.setPlan(plan)
                await op.refreshStatus(plan.id)
              } catch {
                push(t('common.error'), 'err')
              }
            }
          }
        } catch {
          pollErrors.current += 1
          if (pollErrors.current > 10) {
            window.clearInterval(timer)
            setRunId(null)
            push(t('toast.network'), 'err')
          }
        }
      })()
    }, 1000)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId])

  // rehearsal page requested a re-plan with the last params
  useEffect(() => {
    if (op.replanTick > 0) {
      op.clearReplan()
      void startRun(op.lastParams)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [op.replanTick])

  async function doSubmit() {
    if (!op.plan) return
    setSubmitting(true)
    try {
      const res = await submitPlan(op.plan.id)
      push(t('op.submitted'))
      const fresh = await getPlan(op.plan.id).catch(() => null)
      if (fresh) op.setPlan(fresh)
      await op.refreshStatus(fresh?.id ?? op.plan.id)
      void res
    } catch (err) {
      push(err instanceof ApiError ? `${t('op.dispatchFailed')}: ${err.message}` : t('op.dispatchFailed'), 'err')
    } finally {
      setSubmitting(false)
    }
  }

  async function doDispatch() {
    if (!op.plan) return
    setDispatching(true)
    try {
      await dispatchPlan(op.plan.id)
      push(t('op.dispatched'))
      const fresh = await getPlan(op.plan.id).catch(() => null)
      if (fresh) op.setPlan(fresh)
      await op.refreshStatus(fresh?.id ?? op.plan.id)
    } catch (err) {
      push(err instanceof ApiError ? `${t('op.dispatchFailed')}: ${err.message}` : t('op.dispatchFailed'), 'err')
    } finally {
      setDispatching(false)
    }
  }

  async function doCancel() {
    if (!op.plan) return
    try {
      await cancelPlan(op.plan.id)
      push(t('op.cancel'))
      const fresh = await getPlan(op.plan.id).catch(() => null)
      if (fresh) op.setPlan(fresh)
      await op.refreshStatus()
    } catch (err) {
      push(err instanceof ApiError ? err.message : t('common.error'), 'err')
    }
  }

  const running = runId != null
  const showRunPanel = running || run != null
  const planStatus = op.status

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-extrabold text-brand">{t('opnav.planning')}</h1>
      </header>

      {/* ---------- run planner ---------- */}
      <section className="card p-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label className="label" htmlFor="p-time">
              {t('op.timeLimit')}
            </label>
            <input id="p-time" className="field tabular" type="number" min={1} value={timeLimitS} onChange={(e) => setTimeLimitS(e.target.value)} disabled={running} />
          </div>
          <div>
            <label className="label" htmlFor="p-shelf">
              {t('op.minShelf')}
            </label>
            <input id="p-shelf" className="field tabular" type="number" min={0} value={minShelf} onChange={(e) => setMinShelf(e.target.value)} disabled={running} />
          </div>
          <div>
            <label className="label" htmlFor="p-radius">
              {t('op.radius')}
            </label>
            <input id="p-radius" className="field tabular" type="number" min={0.5} step={0.5} value={radius} onChange={(e) => setRadius(e.target.value)} disabled={running} />
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm font-semibold">
            <input type="checkbox" className="h-5 w-5" checked={includePurchases} onChange={(e) => setIncludePurchases(e.target.checked)} disabled={running} />
            {t('op.includePurchases')}
          </label>
          <label className="flex items-center gap-2 text-sm font-semibold">
            <input type="checkbox" className="h-5 w-5" checked={urgentOnly} onChange={(e) => setUrgentOnly(e.target.checked)} disabled={running} />
            {t('pl.urgentOnly')}
          </label>
        </div>
        <label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={demoOnly} disabled={running} onChange={e => setDemoOnly(e.target.checked)}/>{lang === 'hi' ? 'डेमो की 3 दुकानों पर ध्यान दें (1–3)' : 'Focus on the 3 demo shops (1–3)'}</label>
        <p className="mt-1 text-xs text-ink/55">{lang === 'hi' ? '25 दुकानों की योजना के लिए इसे बंद करें।' : 'Turn this off to plan across all 25 shops.'}</p>
        <div className="mt-3">
          <button type="button" className="btn-primary" disabled={running || starting} onClick={() => void startRun()}>
            {running || starting ? t('op.running') : run ? t('op.rerun') : t('op.runPlanner')}
          </button>
        </div>
      </section>

      {/* ---------- run progress / result ---------- */}
      {showRunPanel && (
        <section className="card p-4">
          {running && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm font-semibold">
                <span>{t('op.running')}</span>
                <span className="tabular">{Math.round(run?.progress ?? 0)}%</span>
              </div>
              <ProgressBar value={run?.progress ?? 5} />
              {run && run.log.length > 0 && (
                <pre className="mono max-h-28 overflow-y-auto rounded bg-ivory p-2 text-xs text-ink/70">{run.log.slice(-6).join('\n')}</pre>
              )}
            </div>
          )}

          {!running && run && (
            <div className="space-y-3">
              {run.status === 'error' && <p className="font-semibold text-red-600">{t('op.runFailed')}</p>}

              {run.solver && (
                <div className="flex flex-wrap items-center gap-3">
                  <SolverBadge status={run.solver.status as SolverStatus} provenOptimal={run.solver.proven_optimal} />
                  <span className="text-sm text-ink/70">
                    {t('op.objective')}: <span className="tabular font-bold text-ink">{formatNumber(run.solver.objective, lang)}</span>
                  </span>
                  <span className="tabular text-sm text-ink/70">{t('rc.solveTime', { ms: run.solver.time_ms })}</span>
                </div>
              )}

              {run.plan_id == null && (
                <div>
                  <p className="font-semibold text-ink">{t('op.whyNotNoPlan')}</p>
                  {run.why_not && (
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink/70">
                      {run.why_not.all_purchase && (
                        <li>
                          {t('rc.whyNotAllPurchase')}: {t('rc.coveragePct', { pct: run.why_not.all_purchase.coverage_pct ?? 0 })}
                        </li>
                      )}
                      {run.why_not.pairwise_only && (
                        <li>
                          {t('rc.whyNotPairwise')}: {t('rc.coveragePct', { pct: run.why_not.pairwise_only.coverage_pct ?? 0 })}
                        </li>
                      )}
                      {run.why_not.expiry_move_only && <li>{run.why_not.expiry_move_only.note ?? ''}</li>}
                    </ul>
                  )}
                </div>
              )}

              {run.log.length > 0 && (
                <details>
                  <summary className="cursor-pointer text-sm font-semibold text-ink/70">{t('op.log')}</summary>
                  <pre className="mono mt-1 max-h-40 overflow-y-auto rounded bg-ivory p-2 text-xs text-ink/70">{run.log.join('\n')}</pre>
                </details>
              )}
            </div>
          )}
        </section>
      )}

      {/* ---------- current plan ---------- */}
      {op.plan ? (
        <section className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-lg font-bold text-brand">
              {t('op.plan')} #{op.plan.id} · v{op.plan.version}
            </h2>
            <StatusChip status={String(op.plan.status)} />
            <div className="ml-auto flex gap-2">
              {op.plan.status === 'PROPOSED' && (
                <button type="button" className="btn-accent" disabled={submitting} onClick={() => void doSubmit()}>
                  {submitting ? t('op.requesting') : t('op.requestApprovals')}
                </button>
              )}
              {op.plan.status === 'APPROVED' && (
                <button type="button" className="btn-accent" disabled={dispatching} onClick={() => void doDispatch()}>
                  {dispatching ? t('op.dispatching') : t('op.dispatch')}
                </button>
              )}
              {['PROPOSED', 'AWAITING_APPROVAL', 'APPROVED'].includes(String(op.plan.status)) && <button type="button" className="btn-ghost" disabled={dispatching} onClick={() => void doCancel()}>
                {t('op.cancel')}
              </button>}
            </div>
          </div>

          {planStatus && (
            <section className="card p-4">
              <h3 className="mb-2 text-sm font-bold uppercase tracking-wide text-ink/50">{t('rc.approvals')}</h3>
              {(planStatus.approvals_missing ?? []).length === 0 ? (
                <p className="text-sm font-semibold text-green-700">✓ {t('op.allApproved')}</p>
              ) : (
                <div className="space-y-2">
                  <p className="text-sm font-semibold text-accent">
                    {t('op.approvalsPending')}: {(planStatus.approvals_missing ?? []).map(name).join(', ')}
                  </p>
                  <p className="text-xs text-ink/60">{t('op.collectHint')}</p>
                </div>
              )}
              {(planStatus.approvals ?? []).length > 0 && (
                <ul className="mt-2 space-y-0.5 text-xs text-ink/70">
                  {(planStatus.approvals ?? []).map((a, i) => (
                    <li key={i}>
                      ✓ {name(a.shop_id)} — {a.decision}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          <PlanReceipt plan={op.plan} />

          <section className="card p-4">
            <h3 className="mb-2 text-sm font-bold uppercase tracking-wide text-ink/50">{t('op.sandboxActions')}</h3>
            {(planStatus?.sandbox_actions ?? []).length === 0 ? (
              <p className="text-sm text-ink/60">{t('op.noActions')}</p>
            ) : (
              <ul className="space-y-1.5">
                {(planStatus?.sandbox_actions ?? []).map((a, i) => {
                  const ack = ackOf(a)
                  return (
                    <li key={i} className="flex flex-wrap items-center justify-between gap-2 rounded border border-ink/10 px-3 py-2 text-sm">
                      <span className="font-semibold">{labelOf(a)}</span>
                      <span className="text-xs text-ink/60">
                        {typeof a.shop_id === 'number' ? name(a.shop_id) : ''}
                        {typeof a.qty === 'number' ? ` · ${a.qty}` : ''}
                      </span>
                      {ack === null ? (
                        <span className="chip bg-ink/10 text-ink/60">{t('op.pending')}</span>
                      ) : ack ? (
                        <span className="chip bg-green-100 text-green-800">{t('op.acked')}</span>
                      ) : (
                        <span className="chip bg-red-100 text-red-700">{t('op.notAcked')}</span>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </section>
      ) : (
        !showRunPanel && (
          <div className="card p-5 text-sm text-ink/70">{t('op.noPlanYet')}</div>
        )
      )}

      {/* ---------- plan version history ---------- */}
      <section className="card p-4">
        <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-ink/50">{t('pl.history')}</h2>
        {history.data && history.data.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ink/10 text-left text-xs uppercase tracking-wide text-ink/50">
                  <th className="py-1.5 pr-3">#</th>
                  <th className="py-1.5 pr-3">v</th>
                  <th className="py-1.5 pr-3">{t('ov.status')}</th>
                  <th className="py-1.5 pr-3">{t('rc.solver')}</th>
                  <th className="py-1.5 pr-3">{t('ov.kpiCycles')}</th>
                  <th className="py-1.5 pr-3">{t('ov.coverage')}</th>
                  <th className="py-1.5">{t('ov.kpiCashOut')}</th>
                </tr>
              </thead>
              <tbody>
                {history.data.map((h) => (
                  <tr key={h.id} className="border-b border-ink/5 last:border-0">
                    <td className="py-1.5 pr-3 tabular font-bold"><button className="min-h-[44px] rounded-lg px-2 text-brand underline underline-offset-4" onClick={async () => {try {const p=await getPlan(h.id);op.setPlan(p);await op.refreshStatus(p.id)} catch(e) {push(e instanceof Error ? e.message : t('common.error'),'err')}}} aria-label={(lang === 'hi' ? 'योजना खोलें ' : 'Open plan ') + h.id}>#{h.id}</button></td>
                    <td className="py-1.5 pr-3 tabular">v{h.version}</td>
                    <td className="py-1.5 pr-3"><StatusChip status={h.status} /></td>
                    <td className="py-1.5 pr-3 text-xs">{h.solver_status ?? '—'}</td>
                    <td className="py-1.5 pr-3 tabular">{h.cycles}</td>
                    <td className="py-1.5 pr-3 tabular">{h.coverage_pct}%</td>
                    <td className="py-1.5 tabular">₹{(h.cash_out_paise / 100).toLocaleString('en-IN', { maximumFractionDigits: 0 })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-ink/60">{t('pl.historyEmpty')}</p>
        )}
      </section>
    </div>
  )
}
