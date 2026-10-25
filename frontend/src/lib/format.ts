import type { Lang } from '../i18n'

/** Format integer paise as ₹, e.g. 123450 -> "₹1,234.50" (en-IN) or "₹1,234.50" (hi-IN). */
export function formatMoney(paise: number, lang: Lang): string {
  const nf = new Intl.NumberFormat(lang === 'hi' ? 'hi-IN' : 'en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return nf.format(paise / 100)
}

/** Format a plain integer with Indian digit grouping. */
export function formatNumber(n: number, lang: Lang): string {
  return new Intl.NumberFormat(lang === 'hi' ? 'hi-IN' : 'en-IN').format(n)
}

export function formatDate(iso: string | null, lang: Lang): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(lang === 'hi' ? 'hi-IN' : 'en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function formatDateTime(iso: string | null, lang: Lang): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(lang === 'hi' ? 'hi-IN' : 'en-IN', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function shortHash(hash: string): string {
  if (hash.length <= 10) return hash
  return `${hash.slice(0, 6)}…${hash.slice(-4)}`
}
