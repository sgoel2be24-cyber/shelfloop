import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCaseDirectory, getClusterSummary, sandboxState } from '../../api/client'
import { useI18n } from '../../i18n'
import { useAsyncData } from '../../lib/useAsyncData'
import { StatCard, BarList, Skeleton } from '../../components/StatCard'
import { Icon } from '../../components/Icon'
import { LoopIllustration } from '../../components/LoopIllustration'
import { StatusChip } from '../../components/StatusChip'

const money = (p: number) => '₹' + (p / 100).toLocaleString('en-IN', { maximumFractionDigits: 0 })

export default function Overview() {
  const { t, lang } = useI18n()
  const hi = lang === 'hi'
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<'id' | 'cash' | 'needs'>('id')
  const [page, setPage] = useState(0)
  const { data, loading, error, reload } = useAsyncData(async () => {
    const [directory, summary, state] = await Promise.all([
      getCaseDirectory('cluster-main'), getClusterSummary('cluster-main'), sandboxState(),
    ])
    return { directory, summary, state }
  }, [])
  const summary = data?.summary
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const rows = (data?.directory ?? []).filter(s => !q || [s.name, s.name_hi, s.owner_name, String(s.id)].some(v => v.toLowerCase().includes(q)))
    return rows.sort((a,b) => sort === 'cash' ? b.cash_limit_paise-a.cash_limit_paise : sort === 'needs' ? b.open_needs-a.open_needs : a.id-b.id)
  }, [data, query, sort])
  const pages = Math.max(1, Math.ceil(filtered.length / 8))
  const currentPage = Math.min(page, pages - 1)
  const rows = filtered.slice(currentPage * 8, currentPage * 8 + 8)
  const slowPct = summary?.stock_packs ? Math.min(100, 100 * summary.slow_packs / summary.stock_packs) : 0
  return (
    <div className="space-y-7">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="eyebrow mb-2.5 text-accent">{hi ? 'क्लस्टर की स्थिति' : 'A LITTLE CLARITY. A BETTER TRADING DAY.'}</div>
          <h1 className="page-heading">{hi ? 'हर शेल्फ के लिए नई शुरुआत।' : 'Your neighbourhood, in the loop.'}</h1>
          <p className="page-subtitle">{hi ? 'स्टॉक, ज़रूरतें और अगला सही कदम — एक जगह।' : 'A clear view of your stock, your shops, and what to do next.'}</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={reload} aria-label={t('common.refresh')}><Icon name="refresh" size={16} /></button>
          <Link to="/operator/planning" className="btn-primary"><Icon name="plus" size={16} />{hi ? 'योजना बनाएँ' : 'Create a plan'}</Link>
        </div>
      </header>

      {error && <div className="notice-strip border-red-200 bg-red-50 text-red-800" role="alert">{error} <button className="ml-2 underline" onClick={reload}>{t('common.retry')}</button></div>}
      {loading && !summary && <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{[0,1,2,3].map(i => <Skeleton key={i} className="h-36" />)}</div>}

      {summary && <section className="metric-grid" aria-label={hi ? 'क्लस्टर सारांश' : 'Cluster summary'}>
        <StatCard icon="home" label={t('ov.kpiShops')} value={summary.shops} sub={summary.sharing_on + ' ' + t('ov.kpiSharingOn')} />
        <StatCard icon="box" label={t('ov.kpiStock')} value={summary.stock_packs.toLocaleString('en-IN')} sub={money(summary.stock_value_paise) + (hi ? ' पुष्ट मूल्य' : ' confirmed value')} />
        <StatCard icon="clock" label={t('ov.kpiNearExpiry')} value={money(summary.near_expiry_30_value_paise)} sub={hi ? 'तारीखों की समीक्षा करें' : 'A little attention goes a long way'} tone={summary.near_expiry_30_value_paise > 0 ? 'warn' : 'default'} />
        <StatCard icon="ledger" label={t('ov.kpiNeeds')} value={summary.open_need_packs.toLocaleString('en-IN')} sub={summary.urgent_packs + ' ' + t('misc.urgent')} />
      </section>}

      <div className="overview-columns space-y-5 min-[1100px]:space-y-0">
        <div className="space-y-5 min-w-0">
          <section className="card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 p-5">
              <div><h2 className="section-heading">{hi ? 'आपके क्लस्टर की दुकानें' : 'The shops that make your cluster'}</h2><p className="mt-1.5 text-xs text-ink/55">{hi ? 'साझा स्टॉक से बेहतर अवसर खोजें।' : 'Small shops. Shared possibilities.'}</p></div>
              <span className="chip border border-brand/10 bg-brand/5 text-brand">{filtered.length} {hi ? 'दुकानें' : 'shops'}</span>
            </div>
            <div className="flex flex-wrap gap-2 border-t border-ink/5 px-5 py-3">
              <label className="relative min-w-0 flex-1"><span className="sr-only">{t('ov.searchShops')}</span><Icon name="search" size={16} className="absolute left-3 top-3.5 text-ink/40" /><input className="field pl-9 text-xs" type="search" placeholder={t('ov.searchShops')} value={query} onChange={e => {setQuery(e.target.value);setPage(0)}} /></label>
              <select aria-label={hi ? 'दुकानों का क्रम' : 'Sort shops'} className="field w-auto text-xs" value={sort} onChange={e => {setSort(e.target.value as typeof sort);setPage(0)}}>
                <option value="id">{hi ? 'दुकान संख्या' : 'Shop number'}</option><option value="needs">{hi ? 'सबसे अधिक ज़रूरत' : 'Most needs'}</option><option value="cash">{hi ? 'नकद सीमा' : 'Cash limit'}</option>
              </select>
            </div>
            <div className="overflow-x-auto">
              <table className="cluster-table min-w-[580px]">
                <thead><tr><th>{t('ov.shop')}</th><th>{hi ? 'स्टॉक मूल्य' : 'Stock value'}</th><th>{hi ? 'ज़रूरतें' : 'Needs'}</th><th>{hi ? 'नेटवर्क' : 'Network'}</th></tr></thead>
                <tbody>{rows.map(s => {
                  const unavailable = s.withdrawn || data?.state.withdrawn_shops.includes(s.id)
                  const offline = data?.state.disconnected_shops.includes(s.id)
                  return <tr key={s.id}>
                    <td><div className="flex items-center gap-3"><span className="shop-avatar">{String(s.id).padStart(2,'0')}</span><div><div className="font-semibold">{hi ? s.name_hi || s.name : s.name}</div><div className="mt-1 text-[11px] text-ink/55">{s.owner_name}</div></div></div></td>
                    <td className="tabular font-semibold">{money(s.stock_value_paise)}<div className="mt-1 text-[10px] font-normal text-ink/50">{s.packs} {t('common.packs')}</div></td>
                    <td><span className="tabular font-semibold">{s.need_packs}</span><span className="ml-1 text-[10px] text-ink/50">{t('common.packs')}</span>{s.near_expiry_lots > 0 && <div className="mt-1 text-[10px] text-accent">{s.near_expiry_lots} {hi ? 'तारीखें देखें' : 'date checks'}</div>}</td>
                    <td><span className={'chip ' + (unavailable || offline ? 'bg-amber-50 text-amber-800' : s.sharing_opt_in ? 'bg-[#edf4e6] text-[#4c6e3c]' : 'bg-ink/5 text-ink/60')}><span className={'h-1.5 w-1.5 rounded-full ' + (unavailable || offline ? 'bg-amber-600' : s.sharing_opt_in ? 'bg-[#799c61]' : 'bg-ink/30')} />{unavailable ? (hi ? 'अनुपलब्ध' : 'Unavailable') : offline ? (hi ? 'ऑफलाइन' : 'Offline') : s.sharing_opt_in ? (hi ? 'साझा कर रहे हैं' : 'Sharing') : (hi ? 'निजी' : 'Private')}</span></td>
                  </tr>
                })}</tbody>
              </table>
              {!loading && rows.length === 0 && <p className="p-8 text-center text-sm text-ink/60">{hi ? 'कोई दुकान नहीं मिली। खोज बदलें।' : 'No shops found. Try a different search.'}</p>}
            </div>
            <div className="flex items-center justify-between border-t border-ink/10 px-5 py-3 text-[11px] text-ink/55">
              <span>{filtered.length ? currentPage*8+1 : 0}–{Math.min((currentPage+1)*8,filtered.length)} / {filtered.length}</span>
              <div className="flex gap-2"><button className="btn-ghost min-h-[36px] px-3 py-1 text-xs" disabled={currentPage === 0} onClick={() => setPage(currentPage-1)} aria-label={hi ? 'पिछला पृष्ठ' : 'Previous page'}>←</button><button className="btn-ghost min-h-[36px] px-3 py-1 text-xs" disabled={currentPage+1 >= pages} onClick={() => setPage(currentPage+1)} aria-label={hi ? 'अगला पृष्ठ' : 'Next page'}>→</button></div>
            </div>
          </section>
          {summary && <section className="card p-5"><div className="mb-5 flex items-center justify-between"><h2 className="section-heading">{t('ov.stockByCategory')}</h2><span className="text-[10px] text-ink/50">{hi ? 'पुष्ट खरीद लागत' : 'Confirmed purchase cost'}</span></div><BarList items={summary.top_categories.slice(0,5).map(c => ({label:c.category,value:c.value_paise}))} formatValue={money} /></section>}
        </div>
        <aside className="space-y-5">
          <section className="rounded-2xl border border-[#dce6d2] bg-[#ecf2e4] p-5">
            <div className="eyebrow text-[#60744f]">{hi ? 'साझा संभावनाएँ' : 'BETTER, TOGETHER'}</div>
            <h2 className="mt-3 text-[23px] font-semibold leading-tight tracking-tight text-brand">{hi ? 'रुका हुआ स्टॉक।\nनया रास्ता।' : 'One shop’s surplus.\nAnother’s next move.'}</h2>
            <div className="network-illustration"><LoopIllustration /></div>
            <p className="mb-4 text-[11px] leading-5 text-[#647259]">{hi ? 'उदाहरण मात्र। वास्तविक आदान-प्रदान के लिए स्वीकृत योजना चाहिए।' : 'How the loop works · illustration only. Every actual exchange needs an approved plan.'}</p>
            <Link className="flex min-h-[44px] items-center justify-between rounded-xl bg-white px-4 text-xs font-semibold text-brand" to="/operator/graph">{hi ? 'नेटवर्क देखें' : 'Explore the network'}<span>↗</span></Link>
          </section>
          {summary && <section className="card p-5">
            <h2 className="section-heading">{hi ? 'थोड़ा ध्यान यहाँ' : 'A little attention here'}</h2>
            <div className="mt-5 flex justify-between text-xs"><span className="text-ink/65">{t('ov.kpiSlow')}</span><span className="tabular font-semibold">{Math.round(slowPct)}%</span></div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-ink/5"><div className="h-full rounded-full bg-[#97b97f]" style={{width:slowPct+'%'}} /></div>
            <p className="mt-2 text-[11px] text-ink/55">{summary.slow_packs} {t('common.packs')} · {money(summary.slow_value_paise)}</p>
            <div className="mt-5 flex justify-between border-t border-ink/10 pt-4 text-xs"><span className="text-ink/65">{t('ov.kpiReservations')}</span><strong>{summary.active_reservations}</strong></div>
            {summary.last_plan && <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-ink/10 pt-4"><span className="text-xs">#{summary.last_plan.id} · v{summary.last_plan.version}</span><StatusChip status={summary.last_plan.status} /></div>}
          </section>}
          <p className="px-1 text-[10px] leading-5 text-ink/50">{hi ? 'सिंथेटिक दुकानें और स्टॉक। सभी ऑर्डर अभ्यास के लिए हैं।' : 'Synthetic shops and stock. Orders and transfers run in a sandbox. Inventory moved is not measured savings.'}</p>
        </aside>
      </div>
    </div>
  )
}
