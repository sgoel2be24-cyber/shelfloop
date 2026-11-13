import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { getPlan, getPlanStatus } from '../../api/client'
import type { Plan, PlanStatusResponse, RunParams } from '../../api/types'
import { Icon, type IconName } from '../../components/Icon'
import { LogoMark } from '../../components/Logo'
import { Lang } from '../../components/Lang'
import { useI18n } from '../../i18n'
import type { TKey } from '../../i18n'
import { useSession } from '../../state/Session'

export const DEFAULT_RUN_PARAMS: RunParams = {
  shop_ids: [1, 2, 3],
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
  const { t, lang } = useI18n()
  const { logout } = useSession()
  const navigate = useNavigate()
  const location = useLocation()
  const page = NAV.find((item) => item.to === location.pathname) ?? NAV[0]

  const [plan, setPlanState] = useState<Plan | null>(null)
  const [status, setStatus] = useState<PlanStatusResponse | null>(null)
  const planIdRef = useRef<number | null>(null)
  const [lastParams, setLastParamsState] = useState<RunParams>(DEFAULT_RUN_PARAMS)
  const [replanTick, setReplanTick] = useState(0)

  const setPlan = useCallback((p: Plan | null) => {
    planIdRef.current = p?.id ?? null
    setPlanState(p)
    if (p) sessionStorage.setItem('shelfloop_active_plan',String(p.id))
    else sessionStorage.removeItem('shelfloop_active_plan')
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

  useEffect(() => {
    const id=Number(sessionStorage.getItem('shelfloop_active_plan'))
    if (!id) return
    let alive=true
    getPlan(id).then(p => {if(alive) {setPlan(p);void refreshStatus(p.id)}}).catch(() => sessionStorage.removeItem('shelfloop_active_plan'))
    return () => {alive=false}
  }, [setPlan,refreshStatus])

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
          isActive ? 'active' : ''
        }`
      }
    >
      <Icon name={item.icon} size={19} strokeWidth={2} />
      {t(item.key)}
    </NavLink>
  ))

  return (
    <OperatorContext.Provider value={value}>
      <div className="workspace">
        <aside className="workspace-sidebar">
          <div className="workspace-brand"><LogoMark size={38} /><div>ShelfLoop<small>{lang === 'hi' ? 'पड़ोस का नेटवर्क' : 'THE NEIGHBOURHOOD NETWORK'}</small></div></div>
          <div className="sidebar-caption">{lang === 'hi' ? 'कार्यक्षेत्र' : 'WORKSPACE'}</div>
          <nav aria-label={t('role.operator')}>{navLinks}</nav>
          <div className="sidebar-note">
            <Icon name="graph" size={23} className="mb-3 text-[#d7e8b2]" />
            <div className="text-sm font-semibold text-[#e9f2df]">{lang === 'hi' ? 'एक साथ, बेहतर व्यापार।' : 'Good neighbours. Better trade.'}</div>
            <p className="mt-2">{lang === 'hi' ? 'सही स्टॉक को सही दुकान तक पहुँचाने की योजना बनाएँ।' : 'Connect what one shop has with what another shop needs.'}</p>
          </div>
          <div className="workspace-footer">
            <div className="workspace-avatar">OP</div>
            <div className="min-w-0 flex-1"><div className="text-xs font-semibold">{t('role.operator')}</div><div className="mt-1 text-[10px] text-[#a9bfb0]">{lang === 'hi' ? 'क्लस्टर कार्यक्षेत्र' : 'Cluster workspace'}</div></div>
            <button type="button" aria-label={t('common.logout')} className="rounded-lg p-2 hover:bg-white/10" onClick={() => { logout(); navigate('/login', { replace: true }) }}><Icon name="logout" size={18} /></button>
          </div>
        </aside>
        <div className="min-w-0">
          <header className="workspace-topbar">
            <div className="flex items-center gap-2.5 text-xs text-ink/55">
              <span className="hidden sm:inline">{lang === 'hi' ? 'कार्यक्षेत्र' : 'Workspace'}</span><span className="hidden text-ink/25 sm:inline">/</span>
              <span className="font-semibold text-ink">{t(page.key)}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="mode-pill hidden sm:inline-flex"><span className="status-dot" />{lang === 'hi' ? 'सिंथेटिक डेमो' : 'Synthetic demo'}</span>
              <Lang />
              <button type="button" className="rounded-lg p-2 md:hidden" aria-label={t('common.logout')} onClick={() => { logout(); navigate('/login', { replace: true }) }}><Icon name="logout" size={18} /></button>
            </div>
          </header>
          <nav className="flex gap-1 overflow-x-auto border-b border-ink/10 bg-white px-4 py-2 md:hidden" aria-label={t('role.operator')}>
            {NAV.map(item => <NavLink key={item.to} to={item.to} end={item.to === '/operator'} className={({ isActive }) => 'flex min-h-[44px] shrink-0 items-center gap-2 rounded-lg px-3 text-xs font-semibold ' + (isActive ? 'bg-brand text-white' : 'text-ink/65')}><Icon name={item.icon} size={16} />{t(item.key)}</NavLink>)}
          </nav>
          <main className="workspace-content" id="main-content"><Outlet /></main>
        </div>
      </div>
    </OperatorContext.Provider>
  )
}
