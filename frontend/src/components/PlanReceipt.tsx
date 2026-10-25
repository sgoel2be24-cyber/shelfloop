import { useI18n } from '../i18n'
import { fetchShops, shopLabel } from '../lib/data'
import { formatDateTime, formatMoney, formatNumber, shortHash } from '../lib/format'
import { useAsyncData } from '../lib/useAsyncData'
import type { Plan } from '../api/types'
import { WhyNotBars } from './StatCard'
import { Money } from './Money'
import { SolverBadge } from './SolverBadge'
import { StatusChip } from './StatusChip'
import type { ReactNode } from 'react'

function SectionTitle({ children }: { children: ReactNode }) {
  return <h4 className="mb-2 text-sm font-bold uppercase tracking-wide text-ink/50">{children}</h4>
}

/** Full decision receipt — used on the owner /approvals page and in operator planning. */
function coveragePct(plan: Plan): number {
  const rows = plan.coverage ?? []
  const needed = rows.reduce((a, r) => a + r.qty_needed, 0)
  const covered = rows.reduce((a, r) => a + Math.min(r.qty_covered, r.qty_needed), 0)
  return needed > 0 ? Math.round((100 * covered) / needed) : 0
}

export function PlanReceipt({ plan }: { plan: Plan }) {  const { t, lang } = useI18n()
  const { data: shops } = useAsyncData(() => fetchShops(), [])

  const name = (id: number) => shopLabel(shops?.find((s) => s.id === id), id, lang)
  const m = (paise: number) => formatMoney(paise, lang)

  return (
    <div className="card perforated p-4 sm:p-5">
      {/* ---------- header ---------- */}
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="text-lg font-extrabold text-brand">
          {t('rc.plan')} #{plan.id} · {t('rc.version', { v: plan.version })}
        </h3>
        <StatusChip status={String(plan.status)} />
      </div>
      <div className="mb-4 grid gap-x-6 gap-y-1 text-xs text-ink/60 sm:grid-cols-2">
        <div>
          {t('rc.created')}: <span className="tabular">{formatDateTime(plan.created_at, lang)}</span>
        </div>
        <div className="mono truncate" title={plan.inputs_hash}>
          {t('rc.inputsHash')}: {shortHash(plan.inputs_hash)}
        </div>
        <div className="sm:col-span-2">
          {t('rc.participants')}: {(plan.participants ?? []).map(name).join(' · ')}
        </div>
      </div>

      {/* ---------- cycles ---------- */}
      <section className="mb-4">
        <SectionTitle>{t('rc.cycles')}</SectionTitle>
        {(plan.cycles ?? []).length === 0 && <p className="text-sm text-ink/60">{t('rc.noCycles')}</p>}
        {(plan.cycles ?? []).map((cycle) => {
          const path = (cycle.shop_path ?? []).map(name).join(' → ')
          return (
            <div key={cycle.id} className="mb-3 rounded-lg border border-ink/10 p-3">
              <div className="mb-1 flex flex-wrap items-baseline gap-x-3">
                <span className="text-sm font-bold text-brand">{cycle.id}</span>
                <span className="text-sm text-ink/70">{path}</span>
              </div>

              {(cycle.legs ?? []).map((leg, i) => (
                <div key={`${leg.from_shop}-${leg.to_shop}-${leg.product_id}-${i}`} className="receipt-row">
                  <div className="flex min-w-0 items-start gap-2">
                    <span className="text-xl leading-none" aria-hidden>
                      {leg.emoji}
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-ink">
                        <span className="tabular">{leg.qty}</span> × {leg.product_name}
                      </div>
                      <div className="text-xs text-ink/60">
                        {name(leg.from_shop)} → {name(leg.to_shop)}
                        {leg.expiry_date ? ` · ${t('common.expiry')} ${leg.expiry_date}` : ''}
                        {leg.shelf_days != null ? ` · ${t('rc.shelfDays', { d: leg.shelf_days })}` : ''}
                      </div>
                    </div>
                  </div>
                  <Money paise={leg.value_paise} className="text-sm font-semibold" />
                </div>
              ))}

              <div className="mt-2 border-t border-dashed border-ink/15 pt-2 text-xs">
                <div className="mb-1 font-bold uppercase tracking-wide text-ink/50">{t('rc.balancing')}</div>
                {Object.entries(cycle.balancing_paise_by_shop ?? {}).map(([shopId, paise]) => (
                  <div key={shopId} className="flex items-center justify-between py-0.5">
                    <span>{name(Number(shopId))}</span>
                    <span className={`tabular font-semibold ${paise >= 0 ? 'text-accent' : 'text-brand'}`}>
                      {paise >= 0
                        ? t('rc.pays', { shop: name(Number(shopId)), amount: m(paise) })
                        : t('rc.owed', { shop: name(Number(shopId)), amount: m(-paise) })}
                    </span>
                  </div>
                ))}
                <div className="mt-1 flex justify-between text-ink/70">
                  <span>{t('rc.transportTotal')}</span>
                  <span className="tabular">
                    {t('rc.transport', { amount: m(cycle.transport_paise), per: m(cycle.transport_per_shop_paise) })}
                  </span>
                </div>
                {cycle.slow_packs_redeployed > 0 && (
                  <div className="mt-1 text-ink/70">{t('rc.slowRedeployed', { n: cycle.slow_packs_redeployed })}</div>
                )}
              </div>
            </div>
          )
        })}
      </section>

      {/* ---------- purchases ---------- */}
      <section className="mb-4">
        <SectionTitle>{t('rc.purchases')}</SectionTitle>
        {(plan.purchases ?? []).length === 0 ? (
          <p className="text-sm text-ink/60">{t('rc.noPurchases')}</p>
        ) : (
          <div className="rounded-lg border border-ink/10 p-3">
            {plan.purchases.map((p, i) => (
              <div key={`${p.shop_id}-${p.product_id}-${i}`} className="receipt-row">
                <div className="flex min-w-0 items-start gap-2">
                  <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-accent" aria-hidden />
                  <div>
                    <div className="text-sm font-semibold">
                      {name(p.shop_id)} · <span className="tabular">{p.qty}</span> × {p.product_name}
                    </div>
                    <div className="tabular text-xs text-ink/60">
                      <Money paise={p.unit_price_paise} /> / {t('common.product').toLowerCase()}
                    </div>
                  </div>
                </div>
                <Money paise={p.total_paise} className="text-sm font-semibold text-accent" />
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ---------- coverage ---------- */}
      <section className="mb-4">
        <SectionTitle>{t('rc.coverage')}</SectionTitle>
        {(plan.coverage ?? []).length === 0 ? (
          <p className="text-sm text-ink/60">{t('rc.noCoverage')}</p>
        ) : (
          <div className="rounded-lg border border-ink/10 p-3">
            {plan.coverage.map((c, i) => (
              <div key={`${c.shop_id}-${c.need_id}-${i}`} className="receipt-row">
                <div className="min-w-0">
                  <div className="text-sm font-semibold">
                    {name(c.shop_id)} · {c.product_name}
                  </div>
                  <div className="tabular text-xs text-ink/60">
                    {t('rc.coveredOf', { covered: c.qty_covered, needed: c.qty_needed })} · {t('rc.source')}: {c.source}
                  </div>
                </div>
                {c.urgency === 'urgent' ? (
                  <span className="chip bg-accent/15 text-accent">{t('rc.urgent')}</span>
                ) : (
                  <span className="chip bg-ink/5 text-ink/60">{t('needs.normal')}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ---------- costs ---------- */}
      <section className="mb-4">
        <SectionTitle>{t('rc.costs')}</SectionTitle>
        <div className="rounded-lg border border-ink/10 p-3 text-sm">
          <div className="receipt-row">
            <span>{t('rc.goodsExchanged')}</span>
            <Money paise={plan.costs.goods_value_exchanged_paise} className="font-semibold" />
          </div>
          <div className="receipt-row">
            <span>{t('rc.purchasesTotal')}</span>
            <Money paise={plan.costs.purchases_paise} className="font-semibold" />
          </div>
          <div className="receipt-row">
            <span>{t('rc.transportTotal')}</span>
            <Money paise={plan.costs.transport_paise} className="font-semibold" />
          </div>
          <div className="receipt-row">
            <span>{t('rc.fee')}</span>
            <Money paise={plan.costs.transaction_fee_paise} className="font-semibold" />
          </div>
          <div className="mt-2 border-t border-dashed border-ink/15 pt-2">
            <div className="mb-1 text-xs font-bold uppercase tracking-wide text-ink/50">{t('rc.balancingNet')}</div>
            {Object.entries(plan.costs.balancing_net_by_shop ?? {}).map(([shopId, paise]) => (
              <div key={shopId} className="flex justify-between py-0.5 text-xs">
                <span>{name(Number(shopId))}</span>
                <span className="tabular font-semibold">
                  {paise >= 0 ? '+' : '−'}
                  <Money paise={Math.abs(paise)} />
                </span>
              </div>
            ))}
            <div className="mb-1 mt-2 text-xs font-bold uppercase tracking-wide text-ink/50">
              {t('rc.cashOut')}
              <span className="ml-1 font-normal normal-case">({t('rc.cashOutHint')})</span>
            </div>
            {Object.entries(plan.costs.cash_out_by_shop ?? {}).map(([shopId, paise]) => (
              <div key={shopId} className="flex justify-between py-0.5 text-xs">
                <span>{name(Number(shopId))}</span>
                <Money paise={paise} className="font-semibold" />
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- assumptions ---------- */}
      {(plan.assumptions ?? []).length > 0 && (
        <section className="mb-4">
          <SectionTitle>{t('rc.assumptions')}</SectionTitle>
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink/80">
            {plan.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </section>
      )}

      {/* ---------- solver ---------- */}
      {plan.solver && (
        <section className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <span className="font-bold uppercase tracking-wide text-ink/50">{t('rc.solver')}</span>
          <SolverBadge status={plan.solver.status} provenOptimal={plan.solver.proven_optimal} />
          <span className="text-ink/70">
            {t('rc.objective')}: <span className="tabular font-semibold text-ink">{formatNumber(plan.solver.objective, lang)}</span>
          </span>
          <span className="tabular text-ink/70">{t('rc.solveTime', { ms: plan.solver.time_ms })}</span>
        </section>
      )}

      {/* ---------- why-not: cash for equivalent coverage ---------- */}
      {plan.why_not && (
        <section className="mb-4">
          <SectionTitle>{t('rc.whyNot')}</SectionTitle>
          <div className="rounded-lg border border-ink/10 p-3">
            <WhyNotBars
              rows={[
                { label: t('pl.whyNotAllPurchase'), cashPaise: plan.why_not.all_purchase?.cash_paise ?? 0, coveragePct: plan.why_not.all_purchase?.coverage_pct ?? 0 },
                { label: t('pl.whyNotPairwise'), cashPaise: plan.why_not.pairwise_only?.cash_paise ?? 0, coveragePct: plan.why_not.pairwise_only?.coverage_pct ?? 0 },
                ...(plan.why_not.expiry_move_only?.note
                  ? []
                  : [{ label: t('pl.whyNotExpiry'), cashPaise: plan.why_not.expiry_move_only?.cash_paise ?? 0, coveragePct: plan.why_not.expiry_move_only?.coverage_pct ?? 0 }]),
                {
                  label: t('pl.whyNotThis'),
                  cashPaise: (plan.costs?.purchases_paise ?? 0) + (plan.costs?.transport_paise ?? 0) + (plan.costs?.transaction_fee_paise ?? 0),
                  coveragePct: coveragePct(plan),
                  highlight: true,
                },
              ]}
            />
            {plan.why_not.expiry_move_only?.note && (
              <p className="mt-2 text-xs text-ink/60">{plan.why_not.expiry_move_only.note}</p>
            )}
          </div>
        </section>
      )}

      {/* ---------- approval history ---------- */}
      {(plan.approval_history ?? []).length > 0 && (
        <section>
          <SectionTitle>{t('rc.approvals')}</SectionTitle>
          <div className="space-y-1 text-xs">
            {plan.approval_history.map((a, i) => (
              <div key={i} className="flex flex-wrap items-center gap-x-2">
                <span className={a.decision === 'approved' ? 'text-green-700' : 'text-red-600'}>
                  {a.decision === 'approved' ? '✓' : '✗'}
                </span>
                <span className="font-semibold">{name(a.shop_id)}</span>
                <span className="text-ink/60">
                  {a.decision} · <span className="tabular">{formatDateTime(a.at, lang)}</span> ·{' '}
                  <span className="mono">{shortHash(a.inputs_hash)}</span>
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
