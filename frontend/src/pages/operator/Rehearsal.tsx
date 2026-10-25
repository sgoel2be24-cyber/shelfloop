import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, sandboxInject, sandboxReset, sandboxState } from '../../api/client'
import type { InjectionRecord, SandboxState } from '../../api/types'
import { useI18n } from '../../i18n'
import { fetchProducts, fetchShops, invalidateShops } from '../../lib/data'
import { useAsyncData } from '../../lib/useAsyncData'
import { useToast } from '../../state/Toast'
import { useOperator } from './OperatorShell'

export default function Rehearsal() {
  const { t, lang } = useI18n()
  const { push } = useToast()
  const op = useOperator()
  const navigate = useNavigate()

  const { data, reload } = useAsyncData(async (): Promise<{ shops: Awaited<ReturnType<typeof fetchShops>>; products: Awaited<ReturnType<typeof fetchProducts>>; state: SandboxState } | null> => {
    try {
      const [shops, products, state] = await Promise.all([fetchShops(), fetchProducts(), sandboxState()])
      return { shops, products, state }
    } catch {
      return null
    }
  }, [])

  const shops = data?.shops ?? []
  const products = data?.products ?? []
  const state: SandboxState = data?.state ?? { injections: [], withdrawn_shops: [], disconnected_shops: [] }

  const [wShop, setWShop] = useState(0)
  const [rShop, setRShop] = useState(0)
  const [rProduct, setRProduct] = useState(0)
  const [rQty, setRQty] = useState('5')
  const [dShop, setDShop] = useState(0)
  const [busy, setBusy] = useState(false)
  const [lastEffect, setLastEffect] = useState<string | null>(null)

  const nameOf = (id: number) => {
    const s = shops.find((x) => x.id === id)
    return s ? (lang === 'hi' && s.name_hi ? s.name_hi : s.name) : `#${id}`
  }

  // watch the current plan: after any injection it may flip to NEEDS_OPERATOR
  useEffect(() => {
    if (!op.plan) return
    void op.refreshStatus()
    const timer = window.setInterval(() => void op.refreshStatus(), 5000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [op.plan?.id])

  const planNeedsOperator = String(op.status?.status ?? op.plan?.status ?? '') === 'NEEDS_OPERATOR'

  async function inject(type: 'withdraw_shop' | 'reduce_stock' | 'disconnect', shopId: number, extra?: { product_id?: number; qty?: number }) {
    if (!shopId) {
      push(t('rh.pickShop'), 'err')
      return
    }
    setBusy(true)
    try {
      const res = await sandboxInject({ type, shop_id: shopId, ...extra })
      setLastEffect(res.effect ?? '')
      push(`${t('rh.effect')}: ${res.effect ?? type}`)
      reload()
      await op.refreshStatus()
    } catch (err) {
      push(err instanceof ApiError ? err.message : t('common.error'), 'err')
    } finally {
      setBusy(false)
    }
  }

  async function doReset() {
    setBusy(true)
    try {
      await sandboxReset()
      invalidateShops()
      setLastEffect(null)
      push(t('rh.resetDone'))
      reload()
    } catch (err) {
      push(err instanceof ApiError ? err.message : t('common.error'), 'err')
    } finally {
      setBusy(false)
    }
  }

  function replan() {
    op.requestReplan()
    navigate('/operator/planning')
  }

  const injections: InjectionRecord[] = state.injections ?? []

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold text-brand">{t('rh.title')}</h1>
          <p className="text-sm text-ink/60">{t('rh.subtitle')}</p>
        </div>
        <button type="button" className="btn-ghost" disabled={busy} onClick={() => void doReset()}>
          {t('rh.reset')}
        </button>
      </header>

      {planNeedsOperator && (
        <div className="rounded-lg border-2 border-red-500 bg-red-50 p-4">
          <p className="font-bold text-red-700">⚠️ {t('rh.needsOperator')}</p>
          <p className="mt-1 text-xs text-red-600/80">{t('rh.replanHint')}</p>
          <button type="button" className="btn-danger mt-3" onClick={replan}>
            {t('rh.replan')}
          </button>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-3">
        {/* withdraw shop */}
        <section className="card p-4">
          <h2 className="font-bold text-ink">🚫 {t('rh.withdraw')}</h2>
          <p className="mb-2 mt-0.5 text-xs text-ink/60">{t('rh.withdrawHint')}</p>
          <label className="label" htmlFor="rh-w-shop">
            {t('rh.pickShop')}
          </label>
          <select id="rh-w-shop" className="field" value={wShop} onChange={(e) => setWShop(Number(e.target.value))}>
            <option value={0}>—</option>
            {shops.map((s) => (
              <option key={s.id} value={s.id}>
                {nameOf(s.id)}
              </option>
            ))}
          </select>
          <button type="button" className="btn-danger mt-3 w-full" disabled={busy} onClick={() => void inject('withdraw_shop', wShop)}>
            {t('rh.inject')}
          </button>
        </section>

        {/* reduce stock */}
        <section className="card p-4">
          <h2 className="font-bold text-ink">📉 {t('rh.reduce')}</h2>
          <p className="mb-2 mt-0.5 text-xs text-ink/60">{t('rh.reduceHint')}</p>
          <label className="label" htmlFor="rh-r-shop">
            {t('rh.pickShop')}
          </label>
          <select id="rh-r-shop" className="field" value={rShop} onChange={(e) => setRShop(Number(e.target.value))}>
            <option value={0}>—</option>
            {shops.map((s) => (
              <option key={s.id} value={s.id}>
                {nameOf(s.id)}
              </option>
            ))}
          </select>
          <label className="label mt-2" htmlFor="rh-r-product">
            {t('rh.pickProduct')}
          </label>
          <select id="rh-r-product" className="field" value={rProduct} onChange={(e) => setRProduct(Number(e.target.value))}>
            <option value={0}>—</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.emoji} {p.name}
              </option>
            ))}
          </select>
          <label className="label mt-2" htmlFor="rh-r-qty">
            {t('rh.qty')}
          </label>
          <input id="rh-r-qty" className="field tabular" type="number" min={1} value={rQty} onChange={(e) => setRQty(e.target.value)} />
          <button
            type="button"
            className="btn-danger mt-3 w-full"
            disabled={busy}
            onClick={() => void inject('reduce_stock', rShop, { product_id: rProduct || undefined, qty: Math.max(1, Math.floor(Number(rQty)) || 1) })}
          >
            {t('rh.inject')}
          </button>
        </section>

        {/* disconnect */}
        <section className="card p-4">
          <h2 className="font-bold text-ink">📴 {t('rh.disconnect')}</h2>
          <p className="mb-2 mt-0.5 text-xs text-ink/60">{t('rh.disconnectHint')}</p>
          <label className="label" htmlFor="rh-d-shop">
            {t('rh.pickShop')}
          </label>
          <select id="rh-d-shop" className="field" value={dShop} onChange={(e) => setDShop(Number(e.target.value))}>
            <option value={0}>—</option>
            {shops.map((s) => (
              <option key={s.id} value={s.id}>
                {nameOf(s.id)}
              </option>
            ))}
          </select>
          <button type="button" className="btn-danger mt-3 w-full" disabled={busy} onClick={() => void inject('disconnect', dShop)}>
            {t('rh.inject')}
          </button>
        </section>
      </div>

      {lastEffect && (
        <div className="card p-4">
          <h2 className="mb-1 text-sm font-bold uppercase tracking-wide text-ink/50">{t('rh.effect')}</h2>
          <p className="text-sm text-ink/80">{lastEffect}</p>
        </div>
      )}

      <section className="card p-4">
        <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-ink/50">{t('rh.injections')}</h2>
        {injections.length === 0 ? (
          <p className="text-sm text-ink/60">{t('rh.none')}</p>
        ) : (
          <ul className="space-y-1 text-sm text-ink/80">
            {injections.map((inj, i) => (
              <li key={inj.id ?? inj.injection_id ?? i}>
                <span className="mono font-semibold">{inj.type ?? '?'}</span>
                {typeof inj.shop_id === 'number' ? ` · ${nameOf(inj.shop_id)}` : ''}
                {typeof inj.product_id === 'number' ? ` · product #${inj.product_id}` : ''}
                {typeof inj.qty === 'number' ? ` · −${inj.qty}` : ''}
                {typeof inj.ts === 'string' ? ` · ${inj.ts}` : ''}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
