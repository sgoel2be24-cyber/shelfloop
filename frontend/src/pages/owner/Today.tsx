import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import { getExpiryActions, getNeeds, getPlanStatus, getShopPulse } from '../../api/client'
import { fetchOwnerPlans, pickLatestPlan } from '../../api/discovery'
import type { Need, Plan } from '../../api/types'
import { Countdown, formatMsLeft, useNow } from '../../components/Countdown'
import { Icon } from '../../components/Icon'
import { StatusChip } from '../../components/StatusChip'
import { useI18n } from '../../i18n'
import { fetchShops, shopLabel, useProducts } from '../../lib/data'
import { formatMoney } from '../../lib/format'
import { speak } from '../../lib/speech'
import { useAsyncData } from '../../lib/useAsyncData'
import { useSession } from '../../state/Session'

// ---------------------------------------------------------------------------
// Action-card derivation: facts come from the plan receipt; all wording is
// applied at render time via i18n.
// ---------------------------------------------------------------------------

interface FlowLeg {
  qty: number
  unit: string
  product: string
  valuePaise: number
  incoming: boolean
}

interface CardData {
  key: string
  kind: 'receive' | 'give' | 'purchase' | 'uncovered'
  emoji: string
  legs: FlowLeg[]
  counterparty: string | null
  totalQty: number
  unit: string
  firstProduct: string
  /** balancing for my shop in the touching cycle: positive = I pay, negative = owed to me */
  balancingPaise: number | null
  transportPerShopPaise: number | null
  minShelfDays: number | null
  purchaseTotalPaise: number | null
  coveredProduct: string | null
  slowFlag: boolean
}

function buildCards(plan: Plan | null, myId: number, shopsName: (id: number) => string, productEmoji: (productId: number) => string | null): CardData[] {
  if (!plan) return []
  const groups = new Map<string, CardData>()
  const ordered: CardData[] = []

  for (const cycle of plan.cycles ?? []) {
    for (const leg of cycle.legs ?? []) {
      const incoming = leg.to_shop === myId
      const outgoing = leg.from_shop === myId
      if (!incoming && !outgoing) continue
      const other = incoming ? leg.from_shop : leg.to_shop
      const gkey = `${incoming ? 'in' : 'out'}-${other}`
      let g = groups.get(gkey)
      if (!g) {
        g = {
          key: gkey,
          kind: incoming ? 'receive' : 'give',
          emoji: leg.emoji,
          legs: [],
          counterparty: shopsName(other),
          totalQty: 0,
          unit: 'pack',
          firstProduct: leg.product_name,
          balancingPaise: null,
          transportPerShopPaise: null,
          minShelfDays: null,
          purchaseTotalPaise: null,
          coveredProduct: null,
          slowFlag: false,
        }
        groups.set(gkey, g)
      }
      g.legs.push({ qty: leg.qty, unit: 'pack', product: leg.product_name, valuePaise: leg.value_paise, incoming })
      g.totalQty += leg.qty
      g.emoji = g.legs.length > 1 ? '🔀' : leg.emoji
      if (leg.shelf_days != null) {
        g.minShelfDays = g.minShelfDays === null ? leg.shelf_days : Math.min(g.minShelfDays, leg.shelf_days)
      }
      const myBal = cycle.balancing_paise_by_shop?.[String(myId)]
      if (typeof myBal === 'number') {
        g.balancingPaise = myBal
        g.transportPerShopPaise = cycle.transport_by_shop_paise?.[String(myId)] ?? cycle.transport_per_shop_paise ?? null
      }
      if (incoming) {
        const cov = (plan.coverage ?? []).find((c) => c.shop_id === myId && c.product_id === leg.product_id)
        if (cov) g.coveredProduct = cov.product_name
      } else if ((cycle.slow_packs_redeployed ?? 0) > 0) {
        g.slowFlag = true
      }
    }
  }
  ordered.push(...groups.values())

  for (const p of plan.purchases ?? []) {
    if (p.shop_id !== myId) continue
    ordered.push({
      key: `purchase-${p.product_id}-${p.shop_id}`,
      kind: 'purchase',
      emoji: productEmoji(p.product_id) ?? '🛒',
      legs: [],
      counterparty: null,
      totalQty: p.qty,
      unit: 'pack',
      firstProduct: p.product_name,
      balancingPaise: null,
      transportPerShopPaise: null,
      minShelfDays: null,
      purchaseTotalPaise: p.total_paise,
      coveredProduct: null,
      slowFlag: false,
    })
  }

  return ordered
}

function uncoveredCards(plan: Plan | null, needs: Need[], productEmoji: (productId: number) => string | null): CardData[] {
  if (!plan) return []
  const coveredNeedIds = new Set((plan.coverage ?? []).map((c) => c.need_id))
  return (needs ?? [])
    .filter((n) => !coveredNeedIds.has(n.id))
    .map((n) => ({
      key: `uncovered-${n.id}`,
      kind: 'uncovered' as const,
      emoji: productEmoji(n.product_id) ?? '❓',
      legs: [],
      counterparty: null,
      totalQty: n.qty,
      unit: 'pack',
      firstProduct: n.product_name,
      balancingPaise: null,
      transportPerShopPaise: null,
      minShelfDays: null,
      purchaseTotalPaise: null,
      coveredProduct: null,
      slowFlag: false,
    }))
}

const KIND_ORDER: Record<CardData['kind'], number> = { receive: 0, give: 1, purchase: 2, uncovered: 3 }

// ---------------------------------------------------------------------------

export default function Today() {
  const { t, lang } = useI18n()
  const { session } = useSession()
  const products = useProducts()
  const { data: shops } = useAsyncData(() => fetchShops(), [])
  const { data: plans, error, loading, reload } = useAsyncData(
    () => fetchOwnerPlans(session!.shopId!),
    [session?.shopId],
  )
  const plan = useMemo(() => pickLatestPlan(plans ?? [], session!.shopId!), [plans, session?.shopId])
  const shopId = session!.shopId!
  const ownerName = useMemo(
    () => (shops ?? []).find((x) => x.id === shopId)?.owner_name ?? '',
    [shops, shopId],
  )

  const { data: needs } = useAsyncData(() => getNeeds(session!.shopId!), [session?.shopId])
  const { data: planStatus } = useAsyncData(
    async () => (plan ? getPlanStatus(plan.id) : null),
    [plan?.id],
  )

  const shopsName = (id: number) => shopLabel(shops?.find((s) => s.id === id), id, lang)
  const productEmoji = (productId: number) => products?.find((p) => p.id === productId)?.emoji ?? null

  const cards = useMemo(() => {
    if (plan?.status === 'COMPLETED') return []
    const list = [...buildCards(plan, session!.shopId!, shopsName, productEmoji), ...uncoveredCards(plan, needs ?? [], productEmoji)]
    return list.sort((a, b) => KIND_ORDER[a.kind] - KIND_ORDER[b.kind]).slice(0, 3)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan, needs, shops, lang])

  const expiresAt = useMemo(() => {
    const times = (planStatus?.reservations ?? [])
      .map((r) => r.expires_at)
      .filter((x): x is string => typeof x === 'string')
      .map((x) => Date.parse(x))
      .filter((n) => !Number.isNaN(n))
    if (times.length === 0) return null
    return new Date(Math.min(...times)).toISOString()
  }, [planStatus])

  return (
    <div className="space-y-4">
      <Greeting ownerName={ownerName} />
      <PulseStrip shopId={shopId} />

      <ExpiryStrip shopId={shopId} />

      {plan && (
        <section className="card space-y-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-bold">{lang === 'hi' ? 'पूरा प्लान' : 'Complete plan'} #{plan.id}</h2>
            <StatusChip status={String(plan.status)} />
          </div>
          <p className="text-sm text-ink/70">
            {plan.status === 'COMPLETED'
              ? (lang === 'hi' ? 'सिमुलेशन में आपका कुल नकद: ' : 'Your total cash in this simulation: ')
              : (lang === 'hi' ? 'आपके लिए कुल नकद ज़रूरी: ' : 'Total cash you need ready: ')}
            <strong className="tabular text-ink">{formatMoney(plan.costs.cash_out_by_shop?.[String(shopId)] ?? 0, lang)}</strong>
          </p>
          <p className="text-xs text-ink/60">{plan.status === 'COMPLETED'
            ? (lang === 'hi' ? 'सिमुलेशन पूरा हुआ। स्टॉक और ज़रूरतें अपडेट हो गई हैं। कोई असली भुगतान या डिलीवरी नहीं हुई।' : 'Simulation complete. Stock and needs have been updated. No real payment or delivery occurred.')
            : lang === 'hi'
            ? 'नीचे की सभी अदला-बदली और खरीद एक ही प्लान का हिस्सा हैं। मंज़ूरी पूरे प्लान के लिए होगी।'
            : 'Every exchange and purchase below belongs to one plan. Approval applies to the complete plan.'}</p>
          {plan.status === 'AWAITING_APPROVAL' && (planStatus?.approvals_missing ?? []).includes(shopId) && (
            <Link className="btn-primary" to="/approvals">{lang === 'hi' ? 'पूरा प्लान देखें और निर्णय लें' : 'Review complete plan & decide'}</Link>
          )}
        </section>
      )}

      {plan && String(plan.status) === 'NEEDS_OPERATOR' && (
        <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm font-semibold text-red-700">
          {t('today.planNeedsOperator')}
        </div>
      )}

      {expiresAt && plan && String(plan.status) === 'AWAITING_APPROVAL' && (
        <div className="flex items-center gap-2 text-sm text-ink/70">
          <span>⏳ {t('today.reservation')}</span>
          <Countdown expiresAt={expiresAt} />
        </div>
      )}

      {loading && <p className="text-sm text-ink/60">{t('common.loading')}</p>}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {t('common.error')} — {error}
          <button type="button" className="ml-2 font-bold underline" onClick={reload}>
            {t('common.retry')}
          </button>
        </div>
      )}
      {!loading && !error && cards.length === 0 && !plan && (
        <div className="card p-5 text-sm text-ink/70">{t('today.noPlan')}</div>
      )}

      {cards.map((card) => (
        <ActionCard
          key={card.key}
          card={card}
          expiresAt={expiresAt}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------

interface QAProps {
  icon: string
  question: string
  children: ReactNode
}

function QA({ icon, question, children }: QAProps) {
  return (
    <div className="receipt-row">
      <div className="flex min-w-0 gap-2">
        <span className="shrink-0 text-lg leading-none" aria-hidden>
          {icon}
        </span>
        <div className="min-w-0">
          <div className="text-xs font-bold uppercase tracking-wide text-ink/50">{question}</div>
          <div className="text-sm text-ink">{children}</div>
        </div>
      </div>
    </div>
  )
}

function ActionCard({
  card,
  expiresAt,
}: {
  card: CardData
  expiresAt: string | null
}) {
  const { t, lang } = useI18n()
  const m = (paise: number) => formatMoney(paise, lang)
  const now = useNow(1000)

  // ---- answers to the five questions (data-driven, bilingual templates) ----
  const title =
    card.kind === 'receive'
      ? t('today.cardReceive', { qty: card.totalQty, unit: t('common.packs'), product: card.firstProduct, shop: card.counterparty ?? '' })
      : card.kind === 'give'
        ? t('today.cardGive', { qty: card.totalQty, unit: t('common.packs'), product: card.firstProduct, shop: card.counterparty ?? '' })
        : card.kind === 'purchase'
          ? t('today.cardPurchase', { qty: card.totalQty, unit: t('common.packs'), product: card.firstProduct, amount: m(card.purchaseTotalPaise ?? 0) })
          : t('today.cardUncovered', { product: card.firstProduct })

  let why: string
  if (card.kind === 'receive') {
    why = card.coveredProduct
      ? t('today.whyNeed', { product: card.coveredProduct })
      : card.balancingPaise != null && card.balancingPaise < 0
        ? t('today.whyCash', { amount: m(-card.balancingPaise) })
        : t('today.whyPlan')
  } else if (card.kind === 'give') {
    why =
      card.balancingPaise != null && card.balancingPaise < 0
        ? t('today.whyCash', { amount: m(-card.balancingPaise) })
        : card.slowFlag
          ? t('today.whySlow')
          : t('today.whyReceiveNeed', { shop: card.counterparty ?? '' })
  } else if (card.kind === 'purchase') {
    why = t('today.whyPurchase')
  } else {
    why = t('today.whyPlan')
  }

  const flowLines: string[] = card.legs.map((l) =>
    l.incoming
      ? t('today.flowReceive', { qty: l.qty, product: l.product, value: m(l.valuePaise) })
      : t('today.flowGive', { qty: l.qty, product: l.product, value: m(l.valuePaise) }),
  )
  if (card.kind === 'purchase' && card.purchaseTotalPaise != null) {
    flowLines.push(t('today.flowPay', { amount: m(card.purchaseTotalPaise) }))
  }
  if (card.balancingPaise != null && card.kind !== 'uncovered') {
    flowLines.push(
      card.balancingPaise < 0
        ? t('today.flowOwed', { amount: m(-card.balancingPaise) })
        : t('today.flowPay', { amount: m(card.balancingPaise) }),
    )
  }
  if (flowLines.length === 0) flowLines.push(t('today.flowNothing'))

  const msLeft = expiresAt ? Date.parse(expiresAt) - now : null
  const uncertain: string[] = []
  if (msLeft != null && msLeft > 0 && card.kind !== 'uncovered') {
    uncertain.push(t('today.uReservation', { time: formatMsLeft(msLeft) }))
  }
  if (card.minShelfDays != null && card.minShelfDays < 45) {
    uncertain.push(t('today.uShelf', { days: card.minShelfDays }))
  }
  if (card.transportPerShopPaise != null && card.transportPerShopPaise > 0) {
    uncertain.push(t('today.uTransport', { amount: m(card.transportPerShopPaise) }))
  }
  if (card.balancingPaise != null && card.balancingPaise > 0) {
    uncertain.push(t('today.uBalancing', { amount: m(card.balancingPaise) }))
  }
  if (uncertain.length === 0) uncertain.push(t('today.uNone'))

  const decline: string[] = [t('today.declineGeneric')]
  if (card.kind === 'receive') {
    decline.push(t('today.declineNeed', { product: card.coveredProduct ?? card.firstProduct }))
  } else if (card.kind === 'give') {
    if (card.balancingPaise != null && card.balancingPaise < 0) {
      decline.push(t('today.declineCash', { amount: m(-card.balancingPaise) }))
    } else {
      decline.push(t('today.declineStock'))
    }
  } else if (card.kind === 'purchase') {
    decline.push(t('today.declineNeed', { product: card.firstProduct }))
  }

  const summaryText = [title, why, ...flowLines].join('. ')
  const detailsText = [...uncertain, ...decline].join('. ')

  function hear(kind: 'summary' | 'details') {
    speak(kind === 'summary' ? summaryText : `${summaryText}. ${detailsText}`, lang)
  }

  return (
    <article className="card perforated p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="text-4xl leading-none" aria-hidden>
            {card.emoji}
          </span>
          <h3 className="min-w-0 text-base font-bold text-ink">{title}</h3>
        </div>
        <button
          type="button"
          className="btn-ghost min-h-[40px] shrink-0 px-3 text-lg"
          title={t('today.hear')}
          aria-label={t('today.hear')}
          onClick={() => hear('summary')}
        >
          🔊
        </button>
      </div>

      {card.totalQty > 0 && card.kind !== 'uncovered' && (
        <div className="mt-1">
          <span className="tabular text-3xl font-extrabold text-brand">{card.totalQty}</span>{' '}
          <span className="text-sm text-ink/60">{t('common.packs')}</span>
        </div>
      )}

      <div className="mt-3">
        <QA icon="✅" question={t('q.what')}>
          {title}
        </QA>
        <QA icon="💡" question={t('q.why')}>
          {why}
        </QA>
        <QA icon="🔁" question={t('q.flow')}>
          <ul className="space-y-0.5">
            {flowLines.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </QA>
        <QA icon="❓" question={t('q.uncertain')}>
          <ul className="space-y-0.5">
            {uncertain.map((u, i) => (
              <li key={i}>{u}</li>
            ))}
          </ul>
        </QA>
        <QA icon="🚫" question={t('q.decline')}>
          <ul className="space-y-0.5">
            {decline.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        </QA>
      </div>

      <div className="mt-3 border-t border-ink/10 pt-3">
        <button type="button" className="btn-ghost" onClick={() => hear('details')}>
          {t('today.hearDetails')}
        </button>
      </div>
    </article>
  )
}


// ---------------------------------------------------------------------------
// Expiry advisory strip: near-expiry lots with an absorption suggestion.
// Advisory only — the API marks this a planning threshold, not a safety claim.
// ---------------------------------------------------------------------------

function ExpiryStrip({ shopId }: { shopId: number }) {
  const { t, lang } = useI18n()
  const { data, loading } = useAsyncData(() => getExpiryActions(shopId), [shopId])
  if (loading) return null
  const items = data ?? []
  if (items.length === 0) return null
  return (
    <section className="card border-amber-300 bg-amber-50 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-bold text-amber-800">
          <span aria-hidden>⏰</span>
          {t('today.expiryTitle')}
        </h2>
        <span className="chip bg-amber-200 text-amber-900">{items.length}</span>
      </div>
      <ul className="mt-2 space-y-2">
        {items.slice(0, 4).map((a) => (
          <li key={a.lot_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-amber-200 bg-white px-3 py-2">
            <span className="text-2xl" aria-hidden>
              {a.emoji}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-bold text-ink">
                {a.qty} × {lang === 'hi' && a.product_name_hi ? a.product_name_hi : a.product_name}
              </div>
              <div className="text-xs text-ink/60">
                {formatMoney(a.value_paise, lang)} ·{' '}
                <span className={a.days_left <= 7 ? 'font-bold text-red-600' : 'font-semibold text-amber-700'}>
                  {a.days_left < 0 ? t('today.expiryExpired') : t('today.expiryDays', { d: a.days_left })}
                </span>
                {a.matched_need_packs > 0 && ` · ${t('today.expiryNeeds', { n: a.matched_need_packs })}`}
              </div>
            </div>
            <span
              className={`chip ${
                a.suggestion === 'exchange'
                  ? 'bg-green-100 text-green-800'
                  : a.suggestion === 'return_to_distributor'
                    ? 'bg-brand/10 text-brand'
                    : 'bg-ink/10 text-ink/70'
              }`}
            >
              {a.suggestion === 'exchange'
                ? `🔁 ${t('today.expiryExchange')}`
                : a.suggestion === 'return_to_distributor'
                  ? `↩️ ${t('today.expiryReturn')}`
                  : `⬆️ ${t('today.expiryUseFirst')}`}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] text-amber-700">{t('today.expiryNote')}</p>
    </section>
  )
}


// ---------------------------------------------------------------------------
// Greeting: time-of-day + owner name + date. The human handshake of the app.
// ---------------------------------------------------------------------------

function Greeting({ ownerName }: { ownerName: string }) {
  const { t, lang } = useI18n()
  const timestamp = useNow(60_000)
  const h = new Date(timestamp).getHours()
  const part = h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening'
  const dateStr = new Date(timestamp).toLocaleDateString(lang === 'hi' ? 'hi-IN' : 'en-IN',
    { weekday: 'long', day: 'numeric', month: 'long' })
  return (
    <header className="hand-tilt">
      <h1 className="text-3xl font-extrabold text-brand">
        {t(`today.greet.${part}`, { name: ownerName ? `${ownerName} ji` : '' })}
      </h1>
      <p className="mt-1 text-sm font-semibold text-ink/60">
        <Icon name="calendar" size={14} className="mr-1 inline align-[-2px]" />
        {dateStr} · {t('today.subtitle')}
      </p>
    </header>
  )
}

/** My-shelf pulse: the shop's own numbers in one glance. */
function PulseStrip({ shopId }: { shopId: number }) {
  const { t } = useI18n()
  const { data } = useAsyncData(() => getShopPulse(shopId), [shopId])
  if (!data) return null
  const rupees = (p: number) => `₹${(p / 100).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
  const items = [
    { icon: 'box' as const, label: t('pulse.shelf'), value: `${data.packs} ${t('common.packs')}`, sub: rupees(data.stock_value_paise) },
    { icon: 'clock' as const, label: t('pulse.expiring'), value: rupees(data.near_expiry_value_paise), warn: data.near_expiry_value_paise > 0 },
    { icon: 'graph' as const, label: t('pulse.slow'), value: `${data.slow_packs} ${t('common.packs')}` },
    { icon: 'pencil' as const, label: t('pulse.needs'), value: `${data.need_packs} ${t('common.packs')}` },
  ]
  return (
    <section className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {items.map((it) => (
        <div key={it.label} className={`card px-3 py-2.5 ${it.warn ? 'border-amber-300 bg-amber-50' : ''}`}>
          <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-ink/50">
            <Icon name={it.icon} size={13} strokeWidth={2.2} /> {it.label}
          </div>
          <div className={`text-lg font-extrabold tabular ${it.warn ? 'text-amber-700' : 'text-ink'}`}>{it.value}</div>
        </div>
      ))}
    </section>
  )
}
