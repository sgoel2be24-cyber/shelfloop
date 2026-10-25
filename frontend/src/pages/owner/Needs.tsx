import { useState } from 'react'
import { ApiError, createNeed, deleteNeed, getNeeds } from '../../api/client'
import type { Product } from '../../api/types'
import { useI18n } from '../../i18n'
import { useProducts } from '../../lib/data'
import { useAsyncData } from '../../lib/useAsyncData'
import { useSession } from '../../state/Session'
import { useToast } from '../../state/Toast'
import { Money } from '../../components/Money'

function matches(p: Product, q: string): boolean {
  const s = q.trim().toLowerCase()
  if (!s) return false
  return (
    p.name.toLowerCase().includes(s) ||
    p.name_hi.includes(q.trim()) ||
    p.brand.toLowerCase().includes(s) ||
    p.category.toLowerCase().includes(s) ||
    (p.aliases ?? []).some((a) => a.toLowerCase().includes(s))
  )
}

function ProductSearch({
  products,
  onPick,
  ariaLabel,
}: {
  products: Product[]
  onPick: (p: Product) => void
  ariaLabel: string
}) {
  const { t } = useI18n()
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const found = (products ?? []).filter((p) => matches(p, q)).slice(0, 8)

  return (
    <div className="relative">
      <input
        className="field"
        value={q}
        aria-label={ariaLabel}
        placeholder={t('needs.searchProduct')}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => e.key === 'Escape' && setOpen(false)}
      />
      {open && q.trim() !== '' && (
        <ul className="absolute z-10 mt-1 max-h-60 w-full overflow-y-auto rounded-lg border border-ink/15 bg-white shadow-lg">
          {found.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                className="w-full px-3 py-2.5 text-left hover:bg-ivory"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onPick(p)
                  setQ('')
                  setOpen(false)
                }}
              >
                <span className="mr-1.5 text-lg" aria-hidden>
                  {p.emoji}
                </span>
                <span className="font-semibold">{p.name}</span>
                <span className="ml-1 text-xs text-ink/50">
                  {p.brand} · {p.pack_size}
                </span>
              </button>
            </li>
          ))}
          {found.length === 0 && <li className="px-3 py-2.5 text-sm text-ink/60">{t('needs.noProduct')}</li>}
        </ul>
      )}
    </div>
  )
}

export default function Needs() {
  const { t, lang } = useI18n()
  const { session } = useSession()
  const { push } = useToast()
  const products = useProducts()
  const shopId = session!.shopId!

  const { data: needs, loading, error, reload } = useAsyncData(() => getNeeds(shopId), [shopId])

  const [productId, setProductId] = useState<number | null>(null)
  const [qty, setQty] = useState('1')
  const [urgent, setUrgent] = useState(false)
  const [budget, setBudget] = useState('')
  const [minShelf, setMinShelf] = useState('')
  const [altIds, setAltIds] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const byId = (id: number) => products?.find((p) => p.id === id)

  async function submit() {
    if (!productId) {
      setFormError(t('needs.searchProduct'))
      return
    }
    const n = Math.max(1, Math.floor(Number(qty)) || 0)
    if (n < 1) {
      setFormError(t('needs.qty'))
      return
    }
    const budgetRupees = Number(budget)
    const minShelfDays = Math.floor(Number(minShelf))
    setBusy(true)
    setFormError(null)
    try {
      await createNeed(shopId, {
        product_id: productId,
        qty: n,
        urgency: urgent ? 'urgent' : 'normal',
        ...(altIds.length > 0 ? { alt_product_ids: altIds } : {}),
        ...(budget !== '' && !Number.isNaN(budgetRupees) ? { budget_paise: Math.round(budgetRupees * 100) } : {}),
        ...(minShelf !== '' && minShelfDays > 0 ? { min_shelf_days: minShelfDays } : {}),
      })
      push(t('needs.added'))
      setProductId(null)
      setQty('1')
      setUrgent(false)
      setBudget('')
      setMinShelf('')
      setAltIds([])
      reload()
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : t('common.error'))
    } finally {
      setBusy(false)
    }
  }

  async function remove(id: number) {
    try {
      await deleteNeed(id)
      push(t('needs.deleted'))
      reload()
    } catch (err) {
      push(err instanceof ApiError ? err.message : t('common.error'), 'err')
    }
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-extrabold text-brand">{t('needs.title')}</h1>
        <p className="text-sm text-ink/60">{t('needs.subtitle')}</p>
      </header>

      {/* ---------- add-need form ---------- */}
      <section className="card perforated p-4">
        <h2 className="mb-3 text-lg font-bold text-brand">{t('needs.addTitle')}</h2>
        <div className="space-y-3">
          <div>
            <span className="label">{t('common.product')}</span>
            {productId && byId(productId) ? (
              <div className="flex items-center justify-between gap-2 rounded-lg border border-brand bg-brand/5 px-3 py-2">
                <span className="font-semibold">
                  <span className="mr-1.5 text-lg" aria-hidden>
                    {byId(productId)!.emoji}
                  </span>
                  {byId(productId)!.name}
                </span>
                <button type="button" className="text-sm font-bold text-ink/50 hover:text-ink" onClick={() => setProductId(null)} aria-label={t('common.cancel')}>
                  ✕
                </button>
              </div>
            ) : (
              <ProductSearch products={products ?? []} onPick={(p) => setProductId(p.id)} ariaLabel={t('common.product')} />
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="need-qty">
                {t('needs.qty')}
              </label>
              <input id="need-qty" className="field tabular" type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="need-budget">
                {t('needs.budget')}
              </label>
              <input id="need-budget" className="field tabular" type="number" min={0} step="0.5" value={budget} onChange={(e) => setBudget(e.target.value)} />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-ink/70">{t('needs.urgent')}</span>
            <button
              type="button"
              role="switch"
              aria-checked={urgent}
              onClick={() => setUrgent((u) => !u)}
              className={`inline-flex h-8 w-14 items-center rounded-full border px-1 transition ${urgent ? 'border-accent bg-accent' : 'border-ink/20 bg-white'}`}
            >
              <span className={`h-6 w-6 rounded-full bg-white shadow transition-transform ${urgent ? 'translate-x-6' : ''}`} />
            </button>
            <span className={`chip ${urgent ? 'bg-accent text-white' : 'bg-ink/10 text-ink/60'}`}>{urgent ? t('needs.urgent') : t('needs.normal')}</span>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="need-shelf">
                {t('needs.minShelf')}
              </label>
              <input id="need-shelf" className="field tabular" type="number" min={0} value={minShelf} onChange={(e) => setMinShelf(e.target.value)} />
            </div>
          </div>

          <div>
            <span className="label">{t('needs.alternatives')}</span>
            {altIds.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-2">
                {altIds.map((id) => {
                  const p = byId(id)
                  return (
                    <span key={id} className="chip bg-brand/10 text-brand">
                      {p?.emoji} {p?.name ?? `#${id}`}
                      <button
                        type="button"
                        className="ml-1 font-bold hover:text-red-600"
                        onClick={() => setAltIds((ids) => ids.filter((x) => x !== id))}
                        aria-label={t('common.delete')}
                      >
                        ✕
                      </button>
                    </span>
                  )
                })}
              </div>
            )}
            <ProductSearch
              products={(products ?? []).filter((p) => p.id !== productId && !altIds.includes(p.id))}
              onPick={(p) => setAltIds((ids) => (ids.includes(p.id) ? ids : [...ids, p.id]))}
              ariaLabel={t('needs.alternatives')}
            />
          </div>

          {formError && <p className="text-sm font-semibold text-red-600">{formError}</p>}
          <button type="button" className="btn-accent w-full" disabled={busy} onClick={() => void submit()}>
            {t('needs.add')}
          </button>
        </div>
      </section>

      {/* ---------- list ---------- */}
      {loading && <p className="text-sm text-ink/60">{t('common.loading')}</p>}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {t('common.error')} — {error}
          <button type="button" className="ml-2 font-bold underline" onClick={reload}>
            {t('common.retry')}
          </button>
        </div>
      )}
      {needs && needs.length === 0 && <div className="card p-5 text-sm text-ink/70">{t('needs.empty')}</div>}

      {needs && needs.length > 0 && (
        <ul className="space-y-2">
          {needs.map((n) => {
            const p = byId(n.product_id)
            return (
              <li key={n.id} className="card flex items-center gap-3 p-3">
                <span className="text-3xl" aria-hidden>
                  {p?.emoji ?? '❓'}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-bold">{n.product_name}</div>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-ink/60">
                    {n.urgency === 'urgent' ? (
                      <span className="chip bg-accent/15 text-accent">{t('needs.urgent')}</span>
                    ) : (
                      <span className="chip bg-ink/5 text-ink/60">{t('needs.normal')}</span>
                    )}
                    {n.budget_paise != null && (
                      <span>
                        {t('needs.budget')}: <Money paise={n.budget_paise} />
                      </span>
                    )}
                    {n.min_shelf_days != null && (
                      <span className="tabular">
                        {t('needs.minShelf')}: {n.min_shelf_days}
                      </span>
                    )}
                    <span className="mono">{n.status}</span>
                  </div>
                  {(n.alt_product_ids ?? []).length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {(n.alt_product_ids ?? []).map((id) => (
                        <span key={id} className="chip bg-ink/5 text-ink/60">
                          {byId(id)?.emoji} {byId(id)?.name ?? `#${id}`}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="text-right">
                  <div className="tabular text-3xl font-extrabold text-brand">{n.qty}</div>
                  <div className="text-xs text-ink/50">{lang === 'hi' ? 'पैक' : 'packs'}</div>
                </div>
                <button type="button" className="btn-ghost min-h-[40px] px-3 text-red-600" onClick={() => void remove(n.id)} aria-label={t('common.delete')}>
                  🗑
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
