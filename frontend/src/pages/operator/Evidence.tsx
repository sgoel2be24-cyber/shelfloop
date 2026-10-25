import { useState } from 'react'
import { downloadExport, getEvents } from '../../api/client'
import type { AuditEvent } from '../../api/types'
import { useI18n } from '../../i18n'
import { formatDateTime } from '../../lib/format'
import { useAsyncData } from '../../lib/useAsyncData'
import { useToast } from '../../state/Toast'

export default function Evidence() {
  const { t, lang } = useI18n()
  const { push } = useToast()
  const [exporting, setExporting] = useState(false)
  const [showEvents, setShowEvents] = useState(false)

  const { data: events, error, loading } = useAsyncData(
    async () => (showEvents ? getEvents('cluster-main', 200) : []),
    [showEvents],
  )

  async function doExport() {
    setExporting(true)
    try {
      await downloadExport()
      push(t('toast.saved'))
    } catch (err) {
      push(err instanceof Error ? err.message : t('common.error'), 'err')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-extrabold text-brand">{t('ev.title')}</h1>
        <p className="text-sm text-ink/60">{t('ev.subtitle')}</p>
      </header>

      <section className="card flex flex-wrap items-center justify-between gap-3 p-4">
        <div>
          <h2 className="font-bold text-ink">{t('ev.export')}</h2>
          <p className="text-xs text-ink/60">{t('ev.exportHint')}</p>
        </div>
        <button type="button" className="btn-primary" disabled={exporting} onClick={() => void doExport()}>
          {exporting ? t('common.loading') : `⬇ ${t('ev.export')}`}
        </button>
      </section>

      <section className="card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-bold text-ink">{t('ev.timeline')}</h2>
          <button type="button" className="btn-ghost" onClick={() => setShowEvents((v) => !v)}>
            {t('ev.events')} {showEvents ? '▾' : '▸'}
          </button>
        </div>

        {showEvents && (
          <div className="mt-3">
            {loading && <p className="text-sm text-ink/60">{t('common.loading')}</p>}
            {error && <p className="text-sm text-red-600">{t('common.error')} — {error}</p>}
            {events && events.length === 0 && <p className="text-sm text-ink/60">{t('ev.emptyEvents')}</p>}
            <ol className="relative space-y-3 border-l-2 border-ink/15 pl-4">
              {(events ?? []).map((ev: AuditEvent) => (
                <li key={ev.id} className="relative">
                  <span className="absolute -left-[21.5px] top-1.5 h-3 w-3 rounded-full border-2 border-white bg-brand" aria-hidden />
                  <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
                    <span className="tabular text-xs text-ink/50">{formatDateTime(ev.ts, lang)}</span>
                    <span className="chip bg-brand/10 text-brand">{ev.event_type}</span>
                    <span className="text-xs text-ink/60">
                      {t('ev.actor')}: <b>{ev.actor}</b> · {t('ev.ref')}: <span className="mono">{ev.ref_type}#{ev.ref_id}</span>
                    </span>
                  </div>
                  {ev.payload != null && (
                    <details className="mt-1">
                      <summary className="cursor-pointer text-xs text-ink/50">{t('common.details')}</summary>
                      <pre className="mono mt-1 max-h-40 overflow-auto rounded bg-ivory p-2 text-xs text-ink/70">
                        {JSON.stringify(ev.payload, null, 2)}
                      </pre>
                    </details>
                  )}
                </li>
              ))}
            </ol>
          </div>
        )}
      </section>
    </div>
  )
}
