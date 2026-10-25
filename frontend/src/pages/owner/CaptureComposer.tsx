import { useState } from 'react'
import { ApiError, confirmCaptureRaw, createCapture, inventoryConfirm, newIdemKey } from '../../api/client'
import { enqueueOutbox } from '../../api/outbox'
import type { CaptureConfirmEdit, CaptureResponse } from '../../api/types'
import { useI18n } from '../../i18n'
import { useSpeechInput } from '../../lib/useSpeechInput'
import { useProducts } from '../../lib/data'
import { useToast } from '../../state/Toast'

type Phase = 'input' | 'review' | 'done' | 'manual'

interface Choice {
  product_id: number
  qty: number
  unit: string
}

/** Propose-only capture composer: textarea -> proposals -> confirm-cards. */
export function CaptureComposer({ shopId, onClose, onApplied }: { shopId: number; onClose: () => void; onApplied: () => void }) {
  const { t, lang } = useI18n()
  const speech = useSpeechInput(lang)
  const { push } = useToast()
  const products = useProducts()

  const [phase, setPhase] = useState<Phase>('input')
  const [text, setText] = useState('')
  const [capture, setCapture] = useState<CaptureResponse | null>(null)
  const [choices, setChoices] = useState<Choice[]>([])
  const [idemKey] = useState(() => newIdemKey())
  const [applied, setApplied] = useState<{ type: string; detail: string }[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // manual fallback form
  const [mProductId, setMProductId] = useState(0)
  const [mQty, setMQty] = useState('1')
  const [mExpiry, setMExpiry] = useState('')

  async function propose() {
    if (!text.trim()) return
    setBusy(true)
    setError(null)
    try {
      const res = await createCapture(shopId, text.trim())
      setCapture(res)
      if (res.status === 'failed') {
        setPhase('manual')
      } else {
        setChoices(
          res.proposals.map((p) => ({
            product_id: p.product_id ?? 0,
            qty: p.qty ?? 1,
            unit: p.unit ?? 'pack',
          })),
        )
        setPhase('review')
      }
    } catch (err) {
      setError(err instanceof TypeError ? t('toast.network') : err instanceof ApiError ? err.message : t('common.error'))
    } finally {
      setBusy(false)
    }
  }

  function setChoice(i: number, patch: Partial<Choice>) {
    setChoices((cs) => cs.map((c, j) => (j === i ? { ...c, ...patch } : c)))
  }

  async function confirm() {
    if (!capture) return
    if (choices.some((c) => !c.product_id)) {
      setError(t('capture.pickProduct'))
      return
    }
    const edits: CaptureConfirmEdit[] = capture.proposals.map((p, i) => ({
      index: i,
      product_id: choices[i].product_id,
      qty: Math.max(1, Math.floor(choices[i].qty) || 1),
      unit: choices[i].unit || p.unit || 'pack',
      kind: p.kind,
    }))
    setBusy(true)
    setError(null)
    try {
      const res = await confirmCaptureRaw(capture.capture_id, edits, idemKey)
      setApplied(res.applied ?? [])
      setPhase('done')
      onApplied()
    } catch (err) {
      if (err instanceof TypeError) {
        // network down: stash body + same Idempotency-Key for replay on `online`
        enqueueOutbox({ capture_id: capture.capture_id, edits, idem_key: idemKey })
        push(t('capture.queued'), 'err')
        onClose()
      } else {
        setError(err instanceof ApiError ? err.message : t('common.error'))
      }
    } finally {
      setBusy(false)
    }
  }

  async function submitManual() {
    if (!mProductId) {
      setError(t('capture.pickProduct'))
      return
    }
    const qty = Math.max(1, Math.floor(Number(mQty)) || 1)
    setBusy(true)
    setError(null)
    try {
      await inventoryConfirm(
        shopId,
        [{ product_id: mProductId, qty, ...(mExpiry ? { expiry_date: mExpiry } : {}) }],
        'owner_manual_capture',
      )
      setApplied([{ type: 'stock_update', detail: t('capture.applied') }])
      setPhase('done')
      onApplied()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('common.error'))
    } finally {
      setBusy(false)
    }
  }

  const proposals = capture && capture.status !== 'failed' ? capture.proposals : []

  return (
    <div className="card perforated mb-4 p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <h3 className="text-lg font-bold text-brand">{t('capture.title')}</h3>
        <button type="button" className="btn-ghost min-h-[40px] px-3" onClick={onClose} aria-label={t('common.close')}>
          ✕
        </button>
      </div>

      {phase === 'input' && (
        <div className="space-y-3">
          <p className="text-xs text-ink/60">{t('capture.hint')}</p>
          <textarea
            className="field min-h-[96px]"
            placeholder={t('capture.placeholder')}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-2">
            {speech.supported && (
              <button
                type="button"
                onClick={() => (speech.listening ? speech.stop() : speech.start((transcript) => setText(transcript)))}
                className={`btn min-h-[44px] px-4 ${speech.listening ? 'btn-danger' : 'btn-ghost'}`}
                aria-pressed={speech.listening}
              >
                {speech.listening ? `⏹ ${t('capture.listening')}` : `🎤 ${t('capture.mic')}`}
              </button>
            )}
            {speech.error === 'unsupported' && <span className="text-xs text-ink/60">{t('capture.micUnsupported')}</span>}
          </div>
          <button type="button" className="btn-primary w-full" disabled={busy || !text.trim()} onClick={() => void propose()}>
            {busy ? t('capture.checking') : t('capture.check')}
          </button>
        </div>
      )}

      {phase === 'review' && (
        <div className="space-y-3">
          <p className="text-sm font-semibold text-ink">{t('capture.review')}</p>
          {proposals.length === 0 && <p className="text-sm text-ink/60">{t('capture.empty')}</p>}
          {proposals.map((p, i) => {
            const amb = p.ambiguity
            const chosen = products?.find((pr) => pr.id === choices[i]?.product_id)
            return (
              <div key={i} className={`rounded-lg border p-3 ${amb ? 'border-accent bg-accent/5' : 'border-ink/15'}`}>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className={`chip ${p.kind === 'need' ? 'bg-brand/10 text-brand' : 'bg-green-100 text-green-800'}`}>
                    {p.kind === 'need' ? t('capture.kind.need') : t('capture.kind.stock_update')}
                  </span>
                  <span className="tabular text-xs text-ink/60">
                    {t('capture.confidence', { pct: Math.round((p.confidence ?? 0) * 100) })}
                  </span>
                </div>

                {amb && (
                  <div className="mb-2">
                    <p className="text-sm font-semibold text-accent">{p.question ?? t('capture.clarify')}</p>
                    <div className="mt-1 flex flex-wrap gap-2">
                      {amb.candidates.map((cand) => (
                        <button
                          key={cand.product_id}
                          type="button"
                          onClick={() => setChoice(i, { product_id: cand.product_id })}
                          className={`rounded-full border px-3 py-1.5 text-sm font-semibold transition ${
                            choices[i]?.product_id === cand.product_id
                              ? 'border-brand bg-brand text-white'
                              : 'border-ink/20 bg-white hover:bg-ivory'
                          }`}
                        >
                          <span className="mr-1" aria-hidden>
                            {cand.emoji}
                          </span>
                          {cand.product_name}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {!amb && !p.product_id && (
                  <div className="mb-2">
                    <label className="label" htmlFor={`pick-${i}`}>
                      {t('capture.pickProduct')}
                    </label>
                    <select
                      id={`pick-${i}`}
                      className="field"
                      value={choices[i]?.product_id ?? 0}
                      onChange={(e) => setChoice(i, { product_id: Number(e.target.value) })}
                    >
                      <option value={0}>—</option>
                      {(products ?? []).map((pr) => (
                        <option key={pr.id} value={pr.id}>
                          {pr.emoji} {pr.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="label" htmlFor={`qty-${i}`}>
                      {t('capture.qty')}
                    </label>
                    <input
                      id={`qty-${i}`}
                      className="field tabular"
                      type="number"
                      min={1}
                      value={choices[i]?.qty ?? 1}
                      onChange={(e) => setChoice(i, { qty: Number(e.target.value) })}
                    />
                  </div>
                  <div>
                    <label className="label" htmlFor={`unit-${i}`}>
                      {t('capture.unit')}
                    </label>
                    <input
                      id={`unit-${i}`}
                      className="field"
                      value={choices[i]?.unit ?? 'pack'}
                      onChange={(e) => setChoice(i, { unit: e.target.value })}
                    />
                  </div>
                </div>

                <div className="mt-2 text-sm text-ink/70">
                  {chosen ? (
                    <>
                      <span className="mr-1" aria-hidden>
                        {chosen.emoji}
                      </span>
                      {chosen.name}
                    </>
                  ) : (
                    (p.product_name ?? '—')
                  )}
                  {p.price_ref_paise != null ? ` · ₹${(p.price_ref_paise / 100).toFixed(2)}` : ''}
                </div>
              </div>
            )
          })}

          {error && <p className="text-sm font-semibold text-red-600">{error}</p>}
          <button type="button" className="btn-accent w-full" disabled={busy || proposals.length === 0} onClick={() => void confirm()}>
            {t('capture.confirmAll')}
          </button>
        </div>
      )}

      {phase === 'manual' && (
        <div className="space-y-3">
          <p className="text-sm font-semibold text-accent">{t('capture.failed')}</p>
          <div>
            <label className="label" htmlFor="manual-product">
              {t('capture.manualProduct')}
            </label>
            <select
              id="manual-product"
              className="field"
              value={mProductId}
              onChange={(e) => setMProductId(Number(e.target.value))}
            >
              <option value={0}>—</option>
              {(products ?? []).map((pr) => (
                <option key={pr.id} value={pr.id}>
                  {pr.emoji} {pr.name}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="label" htmlFor="manual-qty">
                {t('capture.manualQty')}
              </label>
              <input id="manual-qty" className="field tabular" type="number" min={1} value={mQty} onChange={(e) => setMQty(e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="manual-expiry">
                {t('capture.manualExpiry')}
              </label>
              <input id="manual-expiry" className="field" type="date" value={mExpiry} onChange={(e) => setMExpiry(e.target.value)} />
            </div>
          </div>
          {error && <p className="text-sm font-semibold text-red-600">{error}</p>}
          <button type="button" className="btn-primary w-full" disabled={busy} onClick={() => void submitManual()}>
            {t('capture.manualAdd')}
          </button>
        </div>
      )}

      {phase === 'done' && (
        <div className="space-y-3">
          <p className="text-sm font-semibold text-green-700">✓ {t('capture.applied')}</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink/80">
            {applied.map((a, i) => (
              <li key={i}>{a.detail}</li>
            ))}
          </ul>
          <button type="button" className="btn-ghost w-full" onClick={onClose}>
            {t('common.close')}
          </button>
        </div>
      )}
    </div>
  )
}
