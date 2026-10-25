import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getPlanStatus } from '../../api/client'
import { fetchOwnerPlans } from '../../api/discovery'
import { Icon, type IconName } from '../../components/Icon'
import { LogoMark } from '../../components/Logo'
import { Lang } from '../../components/Lang'
import { useI18n } from '../../i18n'
import { useSession } from '../../state/Session'
import type { TKey } from '../../i18n'

const TABS: { to: string; icon: IconName; key: TKey }[] = [
  { to: '/today', icon: 'calendar', key: 'tab.today' },
  { to: '/stock', icon: 'box', key: 'tab.stock' },
  { to: '/needs', icon: 'pencil', key: 'tab.needs' },
  { to: '/approvals', icon: 'check', key: 'tab.approvals' },
]

/** Shopkeeper-friendly text size: cycles 100% → 112% → 125%, remembered locally. */
function useTextScale() {
  const [scale, setScaleState] = useState(() => Number(localStorage.getItem('sl_text_scale')) || 100)
  const apply = (v: number) => {
    localStorage.setItem('sl_text_scale', String(v))
    document.documentElement.style.fontSize = `${v}%`
    setScaleState(v)
  }
  useEffect(() => {
    const v = Number(localStorage.getItem('sl_text_scale')) || 100
    document.documentElement.style.fontSize = `${v}%`
  }, [])
  return { scale, cycle: () => apply(scale >= 125 ? 100 : scale + 12) }
}

/** Owner shell: sticky header + fixed bottom tab bar with ≥48px targets. */
export default function OwnerShell() {
  const { t } = useI18n()
  const { session, logout } = useSession()
  const navigate = useNavigate()
  const [pending, setPending] = useState(0)
  const { scale: textScale, cycle: cycleText } = useTextScale()

  // badge: plans awaiting this shop's approval
  useEffect(() => {
    const shopId = session?.shopId
    if (!shopId) return
    let alive = true
    const load = () => {
      fetchOwnerPlans(shopId)
        .then(async (plans) => {
          let n = 0
          for (const p of plans.filter((x) => String(x.status) === 'AWAITING_APPROVAL')) {
            try {
              const st = await getPlanStatus(p.id)
              if ((st.approvals_missing ?? []).includes(shopId)) n += 1
            } catch {
              /* ignore transient errors */
            }
          }
          if (alive) setPending(n)
        })
        .catch(() => {})
    }
    load()
    const timer = window.setInterval(load, 15000)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [session?.shopId])

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-ink/10 bg-ivory/95 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2.5">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <LogoMark size={22} />
              <div className="text-xs font-bold uppercase tracking-wider text-accent">ShelfLoop</div>
            </div>
            <div className="truncate text-base font-bold text-ink">
              {session?.shopName || t('role.owner')}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={cycleText}
              className="flex min-h-[40px] items-center gap-1 rounded-xl border border-ink/20 bg-white px-3 text-sm font-bold text-ink/70 hover:bg-ivory"
              title={t('common.textSize')}
            >
              <Icon name="type" size={16} /> {textScale}%
            </button>
            <Lang />
            <button
              type="button"
              className="btn-ghost min-h-[40px] px-3 text-sm"
              onClick={() => {
                logout()
                navigate('/login', { replace: true })
              }}
            >
              {t('common.logout')}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 pb-28 pt-4">
        <Outlet />
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-ink/10 bg-white" aria-label={t('role.owner')}>
        <div className="mx-auto grid max-w-3xl grid-cols-4">
          {TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              className={({ isActive }) =>
                `flex min-h-[64px] flex-col items-center justify-center gap-0.5 text-xs font-semibold transition-colors ${
                  isActive ? 'bg-brand/5 text-brand' : 'text-ink/60 hover:text-ink'
                }`
              }
            >
              <span className="relative leading-none">
                <Icon name={tab.icon} size={22} strokeWidth={2} />
                {tab.key === 'tab.approvals' && pending > 0 && (
                  <span className="absolute -right-3 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-extrabold text-white">
                    {pending}
                  </span>
                )}
              </span>
              {t(tab.key)}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  )
}
