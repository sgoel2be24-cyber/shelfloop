import { ExchangeGraph } from '../../components/ExchangeGraph'
import { useI18n } from '../../i18n'
import { fetchShops } from '../../lib/data'
import { useAsyncData } from '../../lib/useAsyncData'
import { useOperator } from './OperatorShell'

export default function GraphPage() {
  const { t } = useI18n()
  const op = useOperator()
  const { data: shops } = useAsyncData(() => fetchShops(), [])

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-extrabold text-brand">{t('graph.title')}</h1>
        <p className="text-sm text-ink/60">{t('graph.subtitle')}</p>
      </header>

      {op.plan ? (
        <div className="card p-4">
          <ExchangeGraph plan={op.plan} shops={shops ?? null} />
        </div>
      ) : (
        <div className="card p-5 text-sm text-ink/70">{t('graph.noPlan')}</div>
      )}
    </div>
  )
}
