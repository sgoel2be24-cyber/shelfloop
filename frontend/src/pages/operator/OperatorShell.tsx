import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { getPlanStatus } from '../../api/client'
import type { Plan, PlanStatusResponse, RunParams } from '../../api/types'
import { Icon, type IconName } from '../../components/Icon'
import { LogoMark } from '../../components/Logo'
import { Lang } from '../../components/Lang'
import { useI18n } from '../../i18n'
import type { TKey } from '../../i18n'
import { useSession } from '../../state/Session'

export const DEFAULT_RUN_PARAMS: RunParams = {
  time_limit_ms: 5000,
  min_shelf_days: 14,
  radius_km: 3.0,
  include_purchases: true,
}

interface OperatorCtx {
  plan: Plan | null
  setPlan: (p: Plan | null) => void
  status: PlanStatusResponse | null
  setStatus: (s: PlanStatusResponse | null) => void
  refreshStatus: (planId?: number) => Promise<void>
  lastParams: RunParams
  setLastParams: (p: RunParams) => void
  /** increments when the rehearsal page asks for a re-plan */
  replanTick: number
  requestReplan: () => void
  clearReplan: () => void
}

const OperatorContext = createContext<OperatorCtx | null>(null)

export function useOperator(): OperatorCtx {
  const ctx = useContext(OperatorContext)
  if (!ctx) throw new Error('useOperator must be used inside OperatorShell')
  return ctx
}

const NAV: { to: string; icon: IconName; key: TKey }[] = [
  { to: '/operator', icon: 'home', key: 'opnav.overview' },
  { to: '/operator/planning', icon: 'ledger', key: 'opnav.planning' },
  { to: '/operator/graph', icon: 'graph', key: 'opnav.graph' },
  { to: '/operator/rehearsal', icon: 'bolt', key: 'opnav.rehearsal' },
  { to: '/operator/evidence', icon: 'file', key: 'opnav.evidence' },
]

/** Operator workspace: sidebar nav on desktop, top nav on mobile, shared plan state. */
export default function OperatorShell() {
  const { t } = useI18n()
  const { logout } = useSession()
  const navigate = useNavigate()

  const [plan, setPlanState] = useState<Plan | null>(null)
  const [status, setStatus] = useState<PlanStatusResponse | null>(null)
  const planIdRef = useRef<number | null>(null)
  const [lastParams, setLastParamsState] = useState<RunParams>(DEFAULT_RUN_PARAMS)
  const [replanTick, setReplanTick] = useState(0)

  const setPlan = useCallback((p: Plan | null) => {
    planIdRef.current = p?.id ?? null
    setPlanState(p)
    setStatus(null)
  }, [])

  const refreshStatus = useCallback(async (planId?: number) => {
    const id = planId ?? planIdRef.current
    if (id == null) return
    try {
      setStatus(await getPlanStatus(id))
    } catch {
      // keep previous status; the page surfaces errors elsewhere
    }
  }, [])

  const setLastParams = useCallback((p: RunParams) => setLastParamsState(p), [])
  const requestReplan = useCallback(() => setReplanTick((x) => x + 1), [])
  const clearReplan = useCallback(() => setReplanTick(0), [])

  const value = useMemo(
    () => ({ plan, setPlan, status, setStatus, refreshStatus, lastParams, setLastParams, replanTick, requestReplan, clearReplan }),
    [plan, setPlan, status, refreshStatus, lastParams, setLastParams, replanTick, requestReplan, clearReplan],
  )

  const navLinks = NAV.map((item) => (
    <NavLink
      key={item.to}
      to={item.to}
      end={item.to === '/operator'}
      className={({ isActive }) =>
        `sidebar-link flex min-h-[48px] items-center gap-3 px-3 text-sm font-semibold transition-colors ${
          isActive ? 'bg-brand text-white' : 'text-ink/70 hover:bg-ivory'
        }`
      }
    >
      <Icon name={item.icon} size={19} strokeWidth={2} />
      {t(item.key)}
    </NavLink>
  ))

  return (
    <OperatorContext.Provider value={value}>
      <div className="flex min-h-screen">
        {/* sidebar (desktop) */}
        <aside className="hidden w-60 shrink-0 flex-col border-r border-ink/10 bg-white p-3 md:flex">
          <div className="mb-4 flex items-center gap-2 px-2">
            <LogoMark size={34} />
            <div>
              <div className="text-lg font-extrabold leading-tight text-brand">ShelfLoop</div>
              <div className="text-[10px] font-bold uppercase tracking-wider text-accent">{t('role.operator')}</div>
            </div>
          </div>
          <nav className="flex flex-1 flex-col gap-1" aria-label={t('role.operator')}>
            {navLinks}
          </nav>
          <div className="mt-4 flex flex-col gap-2 border-t border-ink/10 pt-3">
            <Lang />
            <button
              type="button"
              className="btn-ghost min-h-[40px] justify-start text-sm"
              onClick={() => {
                logout()
                navigate('/login', { replace: true })
              }}
            >
              <Icon name="logout" size={17} /> {t('common.logout')}
            </button>
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          {/* mobile top nav */}
          <div className="sticky top-0 z-20 border-b border-ink/10 bg-ivory/95 backdrop-blur md:hidden">
            <div className="flex items-center justify-between gap-2 px-3 py-2">
              <div className="flex items-center gap-1.5 text-base font-extrabold text-brand">
                <LogoMark size={24} /> ShelfLoop
              </div>
              <div className="flex items-center gap-2">
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
            <nav className="flex gap-1 overflow-x-auto px-3 pb-2" aria-label={t('role.operator')}>
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/operator'}
                  className={({ isActive }) =>
                    `flex min-h-[48px] shrink-0 items-center gap-2 rounded-lg px-3 text-sm font-semibold ${
                      isActive ? 'bg-brand text-white' : 'bg-white text-ink/70'
                    }`
                  }
                >
                  <span aria-hidden>{item.icon}</span>
                  {t(item.key)}
                </NavLink>
              ))}
            </nav>
          </div>

          <main className="mx-auto max-w-4xl p-4 md:p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </OperatorContext.Provider>
  )
}
