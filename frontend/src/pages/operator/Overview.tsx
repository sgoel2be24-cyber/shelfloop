import { useMemo, useState } from 'react'
import { getCaseDirectory, getClusterSummary, sandboxState } from '../../api/client'
import type { DirectoryRow } from '../../api/client'
import type { ClusterSummary } from '../../api/types'
import { useI18n } from '../../i18n'
import { useAsyncData } from '../../lib/useAsyncData'
import { Money } from '../../components/Money'
import { BarList, CoverageDonut, Skeleton, StatCard } from '../../components/StatCard'

const rupees = (paise: number) =>
  `₹${(paise / 100).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`

export default function Overview() {
  const { t, lang } = useI18n()
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<'id' | 'cash' | 'needs'>('id')

  const { data: shops, error, loading, reload } = useAsyncData(async () => {
    const [dir, state, summary] = await Promise.all([
      getCaseDirectory('cluster-main').catch(() => null),
      sandboxState(),
      getClusterSummary('cluster-main').catch(() => null),
    ])
    return { dir, state, summary }
  }, [])

  const summary: ClusterSummary | null = shops?.summary ?? null
  const directory: DirectoryRow[] = shops?.dir ?? []

  const filtered = useMemo(() => {
    const list = [...directory]
    const q = query.trim().toLowerCase()
    const matched = q
      ? list.filter(
          (s) =>
            s.name.toLowerCase().includes(q) ||
            s.name_hi.includes(q) ||
            s.owner_name.toLowerCase().includes(q) ||
            String(s.id) === q,
        )
      : list
    if (sort === 'cash') matched.sort((a, b) => b.cash_limit_paise - a.cash_limit_paise)
    else if (sort === 'needs') matched.sort((a, b) => b.open_needs - a.open_needs)
    else matched.sort((a, b) => a.id - b.id)
    return matched
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shops, query, sort])

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold text-brand">{t('ov.title')}</h1>
          <p className="text-sm text-ink/60">{t('ov.subtitle')}</p>
        </div>
        <button type="button" className="btn-ghost" onClick={reload}>
          ⟳ {t('common.refresh')}
        </button>
      </header>

      {loading && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}
      {error && <p className="text-sm text-red-600">{t('common.error')} — {error}</p>}

      {/* ---------- KPI grid ---------- */}
      {summary && (
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <StatCard icon="🏪" label={t('ov.kpiShops')} value={summary.shops} sub={`${summary.sharing_on} ${t('ov.kpiSharingOn')}`} />
          <StatCard icon="📦" label={t('ov.kpiStock')} value={summary.stock_packs.toLocaleString('en-IN')} sub={`${t('ov.kpiWorth')} ${rupees(summary.stock_value_paise)}`} />
          <StatCard
            icon="⏰"
            label={t('ov.kpiNearExpiry')}
            value={rupees(summary.near_expiry_30_value_paise)}
            sub={`${t('ov.kpiWithin14')} ${rupees(summary.near_expiry_14_value_paise)}`}
            tone={summary.near_expiry_30_value_paise > 0 ? 'warn' : 'good'}
          />
          <StatCard icon="🐢" label={t('ov.kpiSlow')} value={`${summary.slow_packs.toLocaleString('en-IN')} ${t('common.packs')}`} sub={`${t('ov.kpiWorth')} ${rupees(summary.slow_value_paise)}`} />
          <StatCard icon="📝" label={t('ov.kpiNeeds')} value={summary.open_need_packs.toLocaleString('en-IN')} sub={`${summary.urgent_packs} ${t('misc.urgent')}`} tone={summary.urgent_packs > 0 ? 'accent' : 'default'} />
          <StatCard icon="🔒" label={t('ov.kpiReservations')} value={summary.active_reservations} sub={t('ov.kpiReservationsSub')} tone={summary.active_reservations > 0 ? 'good' : 'default'} />
        </section>
      )}

      {/* ---------- last plan + category chart ---------- */}
      <div className="grid gap-3 lg:grid-cols-2">
        {summary?.last_plan && (
          <section className="card p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold uppercase tracking-wide text-ink/50">{t('ov.lastPlan')}</h2>
              <span className="chip bg-brand/10 text-brand">#{summary.last_plan.id} · v{summary.last_plan.version}</span>
            </div>
            <div className="mt-3 flex items-center gap-5">
              <CoverageDonut pct={summary.last_plan.coverage_pct} label={t('ov.coverage')} />
              <dl className="flex-1 space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <dt className="text-ink/60">{t('ov.status')}</dt>
                  <dd className="font-bold">{summary.last_plan.status}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink/60">{t('ov.kpiCycles')}</dt>
                  <dd className="tabular font-bold">{summary.last_plan.cycles}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink/60">{t('ov.kpiCashOut')}</dt>
                  <dd className="tabular font-bold">{rupees(summary.last_plan.cash_out_paise)}</dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-ink/60">{t('ov.kpiSlowMoved')}</dt>
                  <dd className="tabular font-bold text-accent">{summary.last_plan.slow_packs} {t('common.packs')}</dd>
                </div>
              </dl>
            </div>
            <a href="/operator/planning" className="mt-3 inline-block text-sm font-bold text-accent hover:underline">
              {t('ov.openPlan')} →
            </a>
          </section>
        )}

        {summary && summary.top_categories.length > 0 && (
          <section className="card p-4">
            <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-ink/50">{t('ov.stockByCategory')}</h2>
            <BarList
              items={summary.top_categories.map((c) => ({ label: c.category, value: c.value_paise }))}
              formatValue={rupees}
            />
          </section>
        )}
      </div>

      {/* ---------- shop directory ---------- */}
      <section className="card p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-bold uppercase tracking-wide text-ink/50">{t('ov.directory')}</h2>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('ov.searchShops')}
            className="field ml-auto h-9 w-48 min-h-0 py-1 text-sm"
          />
          <select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} className="field h-9 w-auto min-h-0 py-0 text-sm">
            <option value="id">{t('ov.sortId')}</option>
            <option value="cash">{t('ov.sortCash')}</option>
            <option value="needs">{t('ov.sortNeeds')}</option>
          </select>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-ink/10 text-left text-xs uppercase tracking-wide text-ink/50">
                <th className="py-2 pr-3">{t('ov.shop')}</th>
                <th className="py-2 pr-3">{t('ov.cashLimit')}</th>
                <th className="py-2 pr-3">{t('ov.lots')}</th>
                <th className="py-2 pr-3">{t('ov.needs')}</th>
                <th className="py-2">{t('stock.share')}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => {
                const withdrawn = (shops?.state.withdrawn_shops ?? []).includes(s.id) || s.withdrawn
                const disconnected = (shops?.state.disconnected_shops ?? []).includes(s.id)
                return (
                  <tr key={s.id} className="border-b border-ink/5 last:border-0 hover:bg-ivory/60">
                    <td className="py-2 pr-3">
                      <div className="flex items-center gap-2">
                        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand/10 text-sm font-extrabold text-brand">
                          {s.id}
                        </span>
                        <div className="min-w-0">
                          <div className="truncate font-semibold text-ink">
                            {lang === 'hi' && s.name_hi ? s.name_hi : s.name}
                          </div>
                          <div className="truncate text-xs text-ink/50">{s.owner_name}</div>
                        </div>
                        {withdrawn && <span className="chip bg-red-100 text-red-700">🚫</span>}
                        {disconnected && <span className="chip bg-amber-100 text-amber-800">📴</span>}
                      </div>
                    </td>
                    <td className="py-2 pr-3 tabular font-semibold">
                      <Money paise={s.cash_limit_paise} />
                      <div className="text-[10px] font-normal text-ink/50 tabular">{s.packs} {t('common.packs')}</div>
                    </td>
                    <td className="py-2 pr-3 tabular">
                      {s.lots}
                      {s.near_expiry_lots > 0 && (
                        <span className="ml-1.5 chip bg-amber-100 text-amber-800" title={t('ov.kpiNearExpiry')}>
                          ⏰ {s.near_expiry_lots}
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-3 tabular">{s.open_needs}</td>
                    <td className="py-2">
                      {s.sharing_opt_in ? (
                        <span className="chip bg-green-100 text-green-700">{t('ov.sharing')}</span>
                      ) : (
                        <span className="chip bg-ink/10 text-ink/60">{t('ov.sharingOff')}</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {(shops?.state.injections ?? []).length > 0 && (
        <section className="card border-amber-300 bg-amber-50 p-4">
          <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-amber-700">{t('rh.injections')}</h2>
          <ul className="space-y-1 text-sm text-ink/80">
            {(shops?.state.injections ?? []).map((inj, i) => (
              <li key={inj.id ?? inj.injection_id ?? i}>
                <span className="mono">{inj.type ?? '?'}</span>
                {typeof inj.shop_id === 'number' ? ` · shop #${inj.shop_id}` : ''}
                {typeof inj.qty === 'number' ? ` · -${inj.qty}` : ''}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
