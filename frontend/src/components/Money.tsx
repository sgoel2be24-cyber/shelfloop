import { useI18n } from '../i18n'
import { formatMoney } from '../lib/format'

/** Integer paise -> ₹1,234.50 (en-IN) with the hi-IN locale when Hindi. */
export function Money({ paise, className }: { paise: number; className?: string }) {
  const { lang } = useI18n()
  return <span className={`tabular whitespace-nowrap ${className ?? ''}`}>{formatMoney(paise, lang)}</span>
}
