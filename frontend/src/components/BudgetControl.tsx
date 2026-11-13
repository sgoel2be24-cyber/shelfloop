import { useState } from 'react'
import { getShopPreferences, saveShopPreferences } from '../api/client'
import { useAsyncData } from '../lib/useAsyncData'
import { useI18n } from '../i18n'
import { formatMoney } from '../lib/format'
import { useToast } from '../state/Toast'

export function BudgetControl({ shopId }: { shopId: number }) {
  const { lang } = useI18n()
  const hi = lang === 'hi'
  const { push } = useToast()
  const { data, error, reload } = useAsyncData(() => getShopPreferences(shopId), [shopId])
  const [editing, setEditing] = useState(false)
  const [budget, setBudget] = useState('')
  const [sharing, setSharing] = useState(false)
  const [busy, setBusy] = useState(false)
  async function save() {
    if (!data) return
    const value = Number(budget)
    if (!budget.trim() || !Number.isFinite(value) || value < 0 || value > 10_000_000 || Math.round(value * 100) < data.held_cash_paise) {
      push(hi ? 'नकद सीमा सही भरें। यह मौजूदा होल्ड से कम नहीं हो सकती।' : 'Enter a valid cash limit that covers existing holds.', 'err'); return
    }
    setBusy(true)
    try {
      await saveShopPreferences(shopId, { expected_version:data.version, cash_limit_paise:Math.round(value*100), sharing_opt_in:sharing })
      setEditing(false); reload(); push(hi ? 'आपकी पसंद सहेज दी गई।' : 'Your preferences have been saved.')
    } catch (e) { push(e instanceof Error ? e.message : 'Could not save', 'err'); reload() }
    finally { setBusy(false) }
  }
  if (error) return <div className="notice-strip" role="alert">{error} <button className="underline" onClick={reload}>{hi ? 'फिर प्रयास करें' : 'Retry'}</button></div>
  if (!data) return null
  return <section className="card p-5">
    <div className="flex items-center justify-between gap-3"><div><div className="eyebrow text-ink/55">{hi ? 'आपकी खर्च सीमा' : 'YOUR CASH LIMIT'}</div><div className="mt-2 text-2xl font-semibold tabular text-brand">{formatMoney(data.cash_limit_paise,lang)}</div></div><button className="btn-ghost" onClick={() => {setBudget(String(data.cash_limit_paise/100));setSharing(data.sharing_opt_in);setEditing(!editing)}}>{hi ? 'बदलें' : 'Change'}</button></div>
    <p className="mt-2 text-xs leading-6 text-ink/60">{hi ? 'योजना इस सीमा के भीतर रहती है। अंतिम ऑर्डर के लिए आपकी स्वीकृति चाहिए।' : 'Plans stay within this limit. Every final order still needs your approval.'}</p>
    {data.held_cash_paise > 0 && <p className="mt-2 text-xs text-accent">{formatMoney(data.held_cash_paise,lang)} {hi ? 'मौजूदा योजनाओं में होल्ड है।' : 'held for existing plans, including exceptions awaiting review.'}</p>}
    {editing && <div className="mt-4 space-y-4 border-t border-ink/10 pt-4"><label className="label">{hi ? 'नकद सीमा (₹)' : 'Cash limit (₹)'}<input className="field mt-1" inputMode="decimal" type="number" min="0" step="0.01" value={budget} onChange={e => setBudget(e.target.value)} /></label><label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={sharing} onChange={e => setSharing(e.target.checked)} />{hi ? 'अनुमत स्टॉक पड़ोस से साझा करें' : 'Allow explicitly marked stock to be shared with neighbours'}</label><div className="flex gap-2"><button className="btn-primary" disabled={busy} onClick={() => void save()}>{hi ? 'सहेजें' : 'Save preferences'}</button><button className="btn-ghost" onClick={() => setEditing(false)}>{hi ? 'रद्द करें' : 'Cancel'}</button></div></div>}
  </section>
}
