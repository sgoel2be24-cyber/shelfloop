import { useEffect, useState } from 'react'
import { flushOutbox, getOutboxEntries } from '../api/outbox'
import { useI18n } from '../i18n'

export function ConnectionNotice() {
  const { lang } = useI18n()
  const [online, setOnline] = useState(navigator.onLine)
  const [entries, setEntries] = useState(getOutboxEntries)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    const update = () => {setOnline(navigator.onLine);setEntries(getOutboxEntries())}
    window.addEventListener('online',update);window.addEventListener('offline',update);window.addEventListener('shelfloop-outbox',update)
    return () => {window.removeEventListener('online',update);window.removeEventListener('offline',update);window.removeEventListener('shelfloop-outbox',update)}
  }, [])
  if (online && entries.length === 0) return null
  return <div className="notice-strip mb-4" role="status">
    {!online && <p>{lang === 'hi' ? 'ऑफलाइन हैं। ड्राफ्ट सहेज सकते हैं; स्वीकृति के लिए कनेक्शन चाहिए।' : 'You are offline. You can save drafts; approvals need a connection.'}</p>}
    {entries.length > 0 && <div className="flex flex-wrap items-center justify-between gap-2"><span>{entries.length} {lang === 'hi' ? 'पुष्टियाँ इस डिवाइस पर लंबित हैं।' : 'confirmations are pending on this device.'}</span><button className="btn-ghost min-h-[36px] text-xs" disabled={busy || !online} onClick={async () => {setBusy(true);try {await flushOutbox()} finally {setEntries(getOutboxEntries());setBusy(false)}}}>{lang === 'hi' ? 'फिर से भेजें' : 'Retry sync'}</button></div>}
    {entries.filter(e => e.error).map(e => <p key={e.idem_key} className="mt-2 text-xs text-red-800">#{e.capture_id}: {e.error}</p>)}
  </div>
}
