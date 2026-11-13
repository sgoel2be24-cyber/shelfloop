import { useMemo, useState } from 'react'
import { useI18n } from '../i18n'
import { shopLabel } from '../lib/data'
import type { Plan, Shop } from '../api/types'
import { Money } from './Money'

const W = 720
const H = 480
const PAD = 90

interface Pt {
  x: number
  y: number
}

const CYCLE_COLORS = ['#174C3C', '#B6532D', '#0E7490', '#687F3A', '#9C4262', '#15803D', '#B45309', '#366B7F']

const mid = (a: Pt, b: Pt): Pt => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 })
const sub = (a: Pt, b: Pt): Pt => ({ x: a.x - b.x, y: a.y - b.y })
const add = (a: Pt, b: Pt): Pt => ({ x: a.x + b.x, y: a.y + b.y })
const mul = (a: Pt, k: number): Pt => ({ x: a.x * k, y: a.y * k })
const vlen = (a: Pt): number => Math.hypot(a.x, a.y) || 1

function trunc(s: string, n = 14): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s
}

/**
 * Interactive inline-SVG exchange graph: shops positioned schematically, cycle legs
 * coloured per cycle, purchases from a supplier node. Click a node to focus its
 * flows; everything else dims.
 */
export function ExchangeGraph({ plan, shops }: { plan: Plan; shops: Shop[] | null }) {
  const { t, lang } = useI18n()
  const [focus, setFocus] = useState<number | null>(null)
  const [showPurchases, setShowPurchases] = useState(false)
  const name = (id: number) => shopLabel(shops?.find((s) => s.id === id), id, lang)

  const known = (plan.participants ?? [])
    .map((id) => shops?.find((s) => s.id === id))
    .filter((s): s is Shop => s !== undefined)
  const nodes: Shop[] =
    known.length > 0
      ? known
      : (plan.participants ?? []).map((id) => ({
          id,
          name: `Shop ${id}`,
          name_hi: `दुकान ${id}`,
          owner_name: '',
          lat: 0,
          lng: 0,
          cash_limit_paise: 0,
          sharing_opt_in: false,
          withdrawn: false, version: 1,
        }))

  const pos = useMemo(() => {
    const m = new Map<number, Pt>()
    nodes.forEach((s, i) => {
      const angle = (i / Math.max(1, nodes.length)) * Math.PI * 2 - Math.PI / 2
      m.set(s.id, {
        x: W / 2 + (W / 2 - PAD) * Math.cos(angle),
        y: H / 2 + 20 + (H / 2 - PAD) * Math.sin(angle),
      })
    })
    return m
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shops, plan.id, plan.version])

  const hasPurchases = showPurchases && (plan.purchases ?? []).length > 0
  const supplier: Pt = { x: W - 65, y: 42 }

  interface Edge {
    d: string
    label: Pt
    text: string
    color: string
    cycleId: string
    from: number
    to: number
    dash?: string
  }
  const edges: Edge[] = []

  ;(plan.cycles ?? []).forEach((cycle, ci) => {
    const legs = cycle.legs ?? []
    const color = CYCLE_COLORS[ci % CYCLE_COLORS.length]
    const pathPts = (cycle.shop_path ?? []).map((id) => pos.get(id)).filter((p): p is Pt => p !== undefined)
    const centroid = pathPts.length
      ? mul(pathPts.reduce((acc, p) => add(acc, p), { x: 0, y: 0 }), 1 / pathPts.length)
      : { x: W / 2, y: H / 2 }

    legs.forEach((leg, i) => {
      const from = pos.get(leg.from_shop)
      const to = pos.get(leg.to_shop)
      if (!from || !to) return
      const direction = mul(sub(to, from), 1 / vlen(sub(to, from)))
      const p1 = add(from, mul(direction, 29))
      const p2 = sub(to, mul(direction, 29))
      let d: string
      let label: Pt
      if (legs.length >= 3) {
        const m = mid(p1, p2)
        const away = mul(sub(m, centroid), 1 / vlen(sub(m, centroid)))
        const bow = Math.max(18, vlen(sub(p2, p1)) * 0.18)
        const c = add(m, mul(away, bow))
        d = `M ${p1.x} ${p1.y} Q ${c.x} ${c.y} ${p2.x} ${p2.y}`
        label = add(mul(p1, 0.25), add(mul(c, 0.5), mul(p2, 0.25)))
      } else if (legs.length === 2) {
        const m = mid(p1, p2)
        const dir = mul(sub(p2, p1), 1 / vlen(sub(p2, p1)))
        const perp: Pt = { x: -dir.y, y: dir.x }
        const c = add(m, mul(perp, i === 0 ? 14 : -14))
        d = `M ${p1.x} ${p1.y} Q ${c.x} ${c.y} ${p2.x} ${p2.y}`
        label = add(mul(p1, 0.25), add(mul(c, 0.5), mul(p2, 0.25)))
      } else {
        d = `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y}`
        label = mid(p1, p2)
      }
      edges.push({
        d,
        label,
        text: `${leg.emoji} ${leg.qty}× ${trunc(leg.product_name, 18)}`,
        color,
        cycleId: cycle.id,
        from: leg.from_shop,
        to: leg.to_shop,
      })
    })
  })

  if (hasPurchases) {
    for (const p of plan.purchases ?? []) {
      const to = pos.get(p.shop_id)
      if (!to) continue
      edges.push({
        d: `M ${supplier.x} ${supplier.y} L ${to.x} ${to.y}`,
        label: mid(supplier, to),
        text: `${p.qty}× ${trunc(p.product_name, 16)}`,
        color: '#E8702A',
        cycleId: 'purch',
        from: -1,
        to: p.shop_id,
        dash: '5 4',
      })
    }
  }

  const isDim = (edgeFrom: number, edgeTo: number) => focus !== null && edgeFrom !== focus && edgeTo !== focus

  const focusLegs = focus === null ? [] : edges.filter((e) => e.from === focus || e.to === focus)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {(plan.cycles ?? []).map((c, i) => (
          <span key={c.id} className="chip" style={{ background: `${CYCLE_COLORS[i % CYCLE_COLORS.length]}14`, color: CYCLE_COLORS[i % CYCLE_COLORS.length] }}>
            {c.id}: {t('graph.cycleN', { n: c.shop_path?.length ?? (c.legs ?? []).length })}
          </span>
        ))}
        <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-xs font-semibold text-ink/70">
          <input type="checkbox" checked={showPurchases} onChange={(e) => setShowPurchases(e.target.checked)} />
          {t('graph.showPurchases')}
        </label>
      </div>

      <p className="text-xs text-ink/60">{lang === 'hi' ? 'सांकेतिक दृश्य — दूरी नक्शे के अनुसार नहीं है। दुकान चुनकर उसका लेन-देन देखें।' : 'Schematic view — positions are not geographic. Select a shop to inspect its flows.'}</p>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="mx-auto h-auto w-full max-w-3xl" role="group" aria-label={t('graph.title')}>
          <defs>
            {CYCLE_COLORS.map((c, i) => (
              <marker key={i} id={`sl-arrow-${i}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill={c} />
              </marker>
            ))}
            <marker id="sl-arrow-purch" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#E8702A" />
            </marker>
          </defs>

          {edges.map((e, i) => {
            const dim = isDim(e.from, e.to)
            return (
              <g key={`edge-${i}`} opacity={dim ? 0.12 : 1} className="transition-opacity">
                <path
                  d={e.d}
                  fill="none"
                  stroke={e.color}
                  strokeWidth={focus !== null && !dim ? 4 : 2.5}
                  strokeDasharray={e.dash}
                  markerEnd={`url(#sl-arrow-${e.cycleId === 'purch' ? 'purch' : CYCLE_COLORS.indexOf(e.color)})`}
                />
                {!dim && (
                  <text
                    x={e.label.x}
                    y={e.label.y - 6}
                    textAnchor="middle"
                    fontSize={11}
                    fontWeight={700}
                    fill={e.color}
                    stroke="#FAF5EC"
                    strokeWidth={3}
                    paintOrder="stroke"
                  >
                    {e.text}
                  </text>
                )}
              </g>
            )
          })}

          {hasPurchases && (
            <g opacity={focus !== null && !edges.some((e) => e.cycleId === 'purch' && (e.from === focus || e.to === focus)) ? 0.3 : 1}>
              <circle cx={supplier.x} cy={supplier.y} r={30} fill="#FFF3E9" stroke="#E8702A" strokeWidth={2} strokeDasharray="4 3" />
              <text x={supplier.x} y={supplier.y + 4} textAnchor="middle" fontSize={10} fontWeight={700} fill="#E8702A">
                {t('graph.supplier')}
              </text>
            </g>
          )}

          {nodes.map((s) => {
            const p = pos.get(s.id)
            if (!p) return null
            const isFocus = focus === s.id
            const dim = focus !== null && !isFocus && !edges.some((e) => (e.from === focus && e.to === s.id) || (e.to === focus && e.from === s.id))
            return (
              <g
                key={s.id}
                role="button"
                tabIndex={0}
                aria-label={`${name(s.id)} — ${t('graph.clickFocus')}`}
                aria-pressed={isFocus}
                onKeyDown={event => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    setFocus(isFocus ? null : s.id)
                  }
                }}
                opacity={dim ? 0.25 : 1}
                className="cursor-pointer transition-opacity"
                onClick={() => setFocus(isFocus ? null : s.id)}
              >
                <title>{name(s.id)} — {t('graph.clickFocus')}</title>
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={isFocus ? 28 : 24}
                  fill={isFocus ? '#174C3C' : '#FFFFFF'}
                  stroke="#174C3C"
                  strokeWidth={2.5}
                  className="transition-all"
                />
                <text x={p.x} y={p.y + 5} textAnchor="middle" fontSize={13} fontWeight={800} fill={isFocus ? '#FFFFFF' : '#174C3C'}>
                  #{s.id}
                </text>
                <rect x={p.x - 82} y={p.y + 29} width={164} height={21} rx={6} fill="#FFFFFF" />
                <text x={p.x} y={p.y + 43} textAnchor="middle" fontSize={11} fill="#21352D">
                  {trunc(name(s.id), 26)}
                </text>
              </g>
            )
          })}

          <g fontSize={11} fontWeight={700}>
            <text x={16} y={H - 12} fill="#1F2430">
              {focus ? t('graph.focused', { name: name(focus) }) : t('graph.hint')}
            </text>
          </g>
        </svg>
      </div>

      {focus !== null && (
        <section className="card border-brand/30 bg-brand/5 p-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-brand">
              #{focus} · {name(focus)}
            </h3>
            <button type="button" className="text-sm font-semibold text-ink/50 hover:text-ink" onClick={() => setFocus(null)}>
              ✕
            </button>
          </div>
          {focusLegs.length === 0 ? (
            <p className="mt-2 text-sm text-ink/60">{t('graph.noFlows')}</p>
          ) : (
            <ul className="mt-2 space-y-1.5 text-sm">
              {focusLegs.map((e, i) => {
                const leg =
                  e.cycleId === 'purch'
                    ? undefined
                    : (plan.cycles ?? []).find((c) => c.id === e.cycleId)?.legs?.find((l) => l.from_shop === e.from && l.to_shop === e.to)
                const purchase =
                  e.cycleId === 'purch'
                    ? (plan.purchases ?? []).find((p) => p.shop_id === e.to && `${p.qty}× ${trunc(p.product_name, 16)}` === e.text)
                    : undefined
                return (
                  <li key={i} className="flex items-center justify-between gap-2 border-t border-dashed border-ink/10 pt-1.5 first:border-0 first:pt-0">
                    <span>
                      <span className="mono mr-1 rounded px-1" style={{ background: `${e.color}18`, color: e.color }}>
                        {e.cycleId}
                      </span>
                      {e.from === -1
                        ? `${t('graph.buy')} ${e.text}`
                        : e.to === focus
                          ? `${t('graph.receiveFrom')} ${name(e.from)}: ${e.text}`
                          : `${t('graph.giveTo')} ${name(e.to)}: ${e.text}`}
                    </span>
                    {leg && <Money paise={leg.value_paise} className="tabular text-xs font-bold text-ink/70" />}
                    {purchase && <Money paise={purchase.total_paise} className="tabular text-xs font-bold text-ink/70" />}
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
