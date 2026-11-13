import { useState } from 'react'
import { ApiError, getStock, inventoryConfirm } from '../../api/client'
import type { Lot } from '../../api/types'
import { useI18n } from '../../i18n'
import { formatMoney } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import { useSession } from '../../state/Session'
import { useToast } from '../../state/Toast'
import { CaptureComposer } from './CaptureComposer'
import { StockLotEditor } from './StockLotEditor'

function ExpiryCell({ lot }: { lot: Lot }) {
  const { t } = useI18n()
  if (lot.days_to_expiry == null) {
    return <span className="text-ink/50">{lot.expiry_date ?? t('stock.noExpiry')}</span>
  }
  const d = lot.days_to_expiry
  const cls = d < 14 ? 'bg-red-100 text-red-700' : d < 30 ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-800'
  return (
    <div className="flex flex-col items-start gap-1">
      <span className="text-xs text-ink/60">{lot.expiry_date ?? '—'}</span>
      <span className={`chip ${cls}`}>{t('stock.days', { d })}</span>
    </div>
  )
}

function Switch({ on, label, hint, disabled, onChange }: { on: boolean; label: string; hint: string; disabled?: boolean; onChange: (next: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      title={hint}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={`inline-flex min-h-[36px] items-center gap-1.5 rounded-full border px-2.5 text-xs font-semibold transition ${
        on ? 'border-brand bg-brand text-white' : 'border-ink/20 bg-white text-ink/60 hover:bg-ivory'
      } disabled:opacity-50`}
    >
      <span aria-hidden>{on ? '☑' : '☐'}</span>
      {label}
    </button>
  )
}

function FloorEditor({ lot, busy, onSave }: { lot: Lot; busy: boolean; onSave: (next: number) => void }) {
  const [value, setValue] = useState(String(lot.retained_floor ?? 0))
  const [saved, setSaved] = useState(String(lot.retained_floor ?? 0))

  function commit() {
    const n = Math.max(0, Math.floor(Number(value)) || 0)
    setValue(String(n))
    if (String(n) !== saved) {
      setSaved(String(n))
      onSave(n)
    }
  }

  return (
    <input
      className="field tabular min-h-[36px] w-20 px-2 py-1 text-sm"
      type="number"
      min={0}
      aria-label={`#${lot.lot_id}`}
      value={value}
      disabled={busy}
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()}
    />
  )
}

export default function Stock() {
  const { t, lang } = useI18n()
  const { session } = useSession()
  const { push } = useToast()
  const shopId = session!.shopId!

  const { data: lots, loading, error, reload } = useAsyncData(() => getStock(shopId), [shopId])
  const [composerOpen, setComposerOpen] = useState(false)
  const [busyLot, setBusyLot] = useState<number | null>(null)

  async function patchLot(lot: Lot, change: Partial<Lot>, okMsg: string) {
    setBusyLot(lot.lot_id)
    try {
      await inventoryConfirm(
        shopId,
        [
          {
            lot_id: lot.lot_id,
            product_id: lot.product_id,
            expected_version: lot.version,
            ...(change.permit_share !== undefined ? { permit_share: change.permit_share } : {}),
            ...(change.slow !== undefined ? { slow: change.slow } : {}),
            ...(change.retained_floor !== undefined ? { retained_floor: change.retained_floor } : {}),
          },
        ],
        'owner_stock_edit',
      )
      push(okMsg)
      reload()
    } catch (err) {
      push(err instanceof ApiError ? err.message : t('stock.editFailed'), 'err')
      reload()
    } finally {
      setBusyLot(null)
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold text-brand">{t('stock.title')}</h1>
          <p className="text-sm text-ink/60">{t('stock.subtitle')}</p>
        </div>
        <button type="button" className="btn-accent shrink-0" onClick={() => setComposerOpen((o) => !o)}>
          + {t('stock.addStock')}
        </button>
      </header>

      {composerOpen && <CaptureComposer shopId={shopId} onClose={() => setComposerOpen(false)} onApplied={reload} />}

      {loading && <p className="text-sm text-ink/60">{t('common.loading')}</p>}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {t('common.error')} — {error}
          <button type="button" className="ml-2 font-bold underline" onClick={reload}>
            {t('common.retry')}
          </button>
        </div>
      )}

      {lots && lots.length === 0 && <div className="card p-5 text-sm text-ink/70">{t('stock.empty')}</div>}

      {lots && lots.length > 0 && <div className="space-y-3 md:hidden">
        {lots.map(lot => <article key={lot.lot_id+'-'+lot.version} className="card p-4">
          <div className="flex items-start justify-between gap-3"><div><h2 className="text-sm font-semibold">{lang === 'hi' ? lot.product_name_hi || lot.product_name : lot.product_name}</h2><p className="mt-1 text-xs text-ink/55">{lot.cost_paise > 0 ? formatMoney(lot.cost_paise,lang) : (lang === 'hi' ? 'लागत की पुष्टि बाकी' : 'Cost not confirmed')}</p></div><span className="rounded-xl bg-brand/5 px-3 py-2 text-xl font-semibold tabular text-brand">{lot.qty}</span></div>
          <div className="mt-3 flex items-center justify-between text-xs"><ExpiryCell lot={lot}/><span>{lot.available_qty} {lang === 'hi' ? 'उपलब्ध' : 'available'} · {lot.reserved_qty} {lang === 'hi' ? 'होल्ड' : 'held'}</span></div>
          <div className="mt-4 flex flex-wrap gap-2"><Switch on={lot.permit_share} label={t('stock.share')} hint={t('stock.shareHint')} disabled={busyLot === lot.lot_id} onChange={next=>void patchLot(lot,{permit_share:next},t('stock.saved'))}/><Switch on={lot.slow} label={t('stock.slow')} hint={t('stock.slowHint')} disabled={busyLot === lot.lot_id} onChange={next=>void patchLot(lot,{slow:next},t('stock.saved'))}/></div>
          <StockLotEditor lot={lot} shopId={shopId} onSaved={reload}/>
        </article>)}
      </div>}
      {lots && lots.length > 0 && (
        <div className="card hidden overflow-x-auto md:block">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead>
              <tr className="border-b border-ink/10 text-xs uppercase tracking-wide text-ink/50">
                <th className="px-3 py-2">{t('stock.colProduct')}</th>
                <th className="px-3 py-2 text-right">{t('stock.colQty')}</th>
                <th className="px-3 py-2 text-right">{t('stock.colReserved')}</th>
                <th className="px-3 py-2 text-right">{t('stock.colAvailable')}</th>
                <th className="px-3 py-2">{t('stock.colExpiry')}</th>
                <th className="px-3 py-2">{t('stock.share')}</th>
                <th className="px-3 py-2">{t('stock.slow')}</th>
                <th className="px-3 py-2">{t('stock.floor')}</th>
              </tr>
            </thead>
            <tbody>
              {lots.map((lot) => (
                <tr key={lot.lot_id} className="border-b border-dashed border-ink/10 last:border-0">
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="text-2xl leading-none" aria-hidden>
                        {lot.emoji}
                      </span>
                      <div>
                        <div className="font-semibold">{lot.product_name}</div>
                        <div className="tabular text-xs text-ink/50">{lot.cost_paise > 0 ? formatMoney(lot.cost_paise, lang) : (lang === 'hi' ? 'लागत अज्ञात' : 'Cost unknown')}</div>
                        <StockLotEditor key={lot.version} lot={lot} shopId={shopId} onSaved={reload}/>
                      </div>
                    </div>
                  </td>
                  <td className="tabular px-3 py-2 text-right text-2xl font-extrabold text-brand">{lot.qty}</td>
                  <td className="tabular px-3 py-2 text-right text-ink/70">{lot.reserved_qty}</td>
                  <td className="tabular px-3 py-2 text-right font-semibold">{lot.available_qty}</td>
                  <td className="px-3 py-2">
                    <ExpiryCell lot={lot} />
                  </td>
                  <td className="px-3 py-2">
                    <Switch
                      on={lot.permit_share}
                      label={t('stock.share')}
                      hint={t('stock.shareHint')}
                      disabled={busyLot === lot.lot_id}
                      onChange={(next) => void patchLot(lot, { permit_share: next }, t('stock.saved'))}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <Switch
                      on={lot.slow}
                      label={t('stock.slow')}
                      hint={t('stock.slowHint')}
                      disabled={busyLot === lot.lot_id}
                      onChange={(next) => void patchLot(lot, { slow: next }, t('stock.saved'))}
                    />
                  </td>
                  <td className="px-3 py-2" title={t('stock.floorHint')}>
                    <FloorEditor
                      key={`${lot.lot_id}-${lot.version}`}
                      lot={lot}
                      busy={busyLot === lot.lot_id}
                      onSave={(next) => void patchLot(lot, { retained_floor: next }, t('stock.saved'))}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
