import { useState } from 'react'
import { inventoryConfirm } from '../../api/client'
import type { Lot } from '../../api/types'
import { useI18n } from '../../i18n'

export function StockLotEditor({ lot, shopId, onSaved }: {lot:Lot;shopId:number;onSaved:()=>void}) {
  const { lang } = useI18n()
  const [qty,setQty] = useState(String(lot.qty))
  const [cost,setCost] = useState(lot.cost_paise > 0 ? String(lot.cost_paise/100) : '')
  const [expiry,setExpiry] = useState(lot.expiry_date ?? '')
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  async function save() {
    const count=Number(qty), amount=Number(cost)
    if (!qty.trim() || !Number.isInteger(count) || count < lot.retained_floor || (cost && (!Number.isFinite(amount) || amount <= 0))) {
      setError(lang === 'hi' ? 'पैक संख्या और लागत सही भरें।' : 'Check the whole-pack quantity, retained floor and purchase cost.');return
    }
    setBusy(true);setError('')
    try {
      await inventoryConfirm(shopId,[{lot_id:lot.lot_id,product_id:lot.product_id,expected_version:lot.version,qty:count,...(cost ? {cost_paise:Math.round(amount*100)} : {}),...(expiry ? {expiry_date:expiry} : {})}],'owner_lot_details')
      onSaved()
    } catch(e) {setError(e instanceof Error ? e.message : 'Could not save')}
    finally {setBusy(false)}
  }
  return <details className="mt-3 border-t border-ink/10 pt-3">
    <summary className="min-h-[36px] cursor-pointer text-xs font-semibold text-brand">{lang === 'hi' ? 'संख्या, लागत या तारीख बदलें' : 'Edit quantity, cost or date'}</summary>
    <div className="mt-3 grid gap-3 sm:grid-cols-3">
      <label className="label">{lang === 'hi' ? 'पैक संख्या' : 'Whole packs'}<input className="field mt-1" type="number" min={lot.retained_floor} step="1" value={qty} onChange={e=>setQty(e.target.value)} /></label>
      <label className="label">{lang === 'hi' ? 'प्रति पैक लागत (₹)' : 'Cost per pack (₹)'}<input className="field mt-1" type="number" min="0.01" step="0.01" value={cost} placeholder={lang === 'hi' ? 'अज्ञात' : 'Unknown'} onChange={e=>setCost(e.target.value)} /></label>
      <label className="label">{lang === 'hi' ? 'लेबल की तारीख' : 'Label expiry date'}<input className="field mt-1" type="date" value={expiry} onChange={e=>setExpiry(e.target.value)} /></label>
    </div>
    {error && <p className="mb-2 text-xs text-red-700" role="alert">{error}</p>}
    <button type="button" className="btn-primary mt-1" disabled={busy} onClick={()=>void save()}>{lang === 'hi' ? 'पुष्टि करके सहेजें' : 'Confirm and save'}</button>
  </details>
}
