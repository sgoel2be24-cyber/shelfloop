import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, createSession } from '../api/client'
import type { Role, Shop } from '../api/types'
import { Icon } from '../components/Icon'
import { LogoMark, ShopScene } from '../components/Logo'
import { Lang } from '../components/Lang'
import { useI18n } from '../i18n'
import { useShops } from '../lib/data'
import { useSession } from '../state/Session'
import { useToast } from '../state/Toast'

export default function Login() {
  const { t, lang } = useI18n()
  const { login } = useSession()
  const { push } = useToast()
  const navigate = useNavigate()
  const { shops, error: shopsError } = useShops()

  const [role, setRole] = useState<Role | null>(null)
  const [pin, setPin] = useState('')
  const [selected, setSelected] = useState<Shop | null>(null)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = shops ?? []
    if (!q) return list
    return list.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        (s.name_hi ?? '').includes(query.trim()) ||
        s.owner_name.toLowerCase().includes(q),
    )
  }, [shops, query])

  async function signIn() {
    if (!role) return
    if (role === 'owner' && !selected) {
      setError(t('login.selectShopFirst'))
      return
    }
    if (!pin.trim()) {
      setError(t('login.pin'))
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await createSession(role, role === 'owner' ? selected!.id : null, pin.trim())
      login({ token: res.token, role: res.role, shopId: res.shop_id, shopName: res.shop_name })
      navigate(res.role === 'owner' ? '/today' : '/operator', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && [400, 401, 403].includes(err.status)) {
        setError(t('login.wrongPin'))
      } else if (err instanceof TypeError) {
        setError(t('toast.network'))
      } else {
        setError(t('common.error'))
        push(err instanceof Error ? err.message : t('common.error'), 'err')
      }
    } finally {
      setBusy(false)
    }
  }

  function pickRole(r: Role) {
    setRole(r)
    setPin('')
    setError(null)
    setSelected(null)
  }

  const shopName = (s: Shop) => (lang === 'hi' && s.name_hi ? s.name_hi : s.name)

  return (
    <div className="relative mx-auto flex min-h-screen max-w-md flex-col px-5 py-6">
      <div className="absolute right-5 top-5">
        <Lang />
      </div>

      <header className="mt-8 mb-6">
        <div className="flex items-center gap-2.5">
          <LogoMark size={44} />
          <div>
            <h1 className="text-3xl font-extrabold leading-none text-brand">ShelfLoop</h1>
            <p className="mt-1 text-sm text-ink/60">{t('login.tagline')}</p>
          </div>
        </div>
        <ShopScene className="mt-4 w-full max-w-sm" />
      </header>

      {!role && (
        <section>
          <h2 className="mb-3 text-lg font-bold">{t('login.pickRole')}</h2>
          <div className="grid gap-3">
            <button type="button" className="card flex items-center gap-4 p-5 text-left transition hover:-translate-y-0.5 hover:border-brand hover:shadow-md" onClick={() => pickRole('owner')}>
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand/10 text-brand">
                <Icon name="box" size={24} strokeWidth={2} />
              </span>
              <span>
                <span className="block text-lg font-bold text-brand">{t('role.owner')}</span>
                <span className="block text-xs text-ink/60">{t('login.ownerHint')}</span>
              </span>
              <span className="ml-auto text-ink/30">→</span>
            </button>
            <button type="button" className="card flex items-center gap-4 p-5 text-left transition hover:-translate-y-0.5 hover:border-brand hover:shadow-md" onClick={() => pickRole('operator')}>
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/10 text-accent">
                <Icon name="ledger" size={24} strokeWidth={2} />
              </span>
              <span>
                <span className="block text-lg font-bold text-brand">{t('role.operator')}</span>
                <span className="block text-xs text-ink/60">{t('login.operatorHint')}</span>
              </span>
              <span className="ml-auto text-ink/30">→</span>
            </button>
          </div>
        </section>
      )}

      {role === 'owner' && (
        <section className="space-y-4">
          <div>
            <label className="label" htmlFor="shop-search">
              {t('login.chooseShop')}
            </label>
            <input
              id="shop-search"
              className="field"
              type="search"
              placeholder={t('login.searchShop')}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
            {shopsError && <p className="text-sm text-red-600">{shopsError}</p>}
            {!shops && !shopsError && <p className="text-sm text-ink/60">{t('misc.loadingShops')}</p>}
            {filtered.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => setSelected(s)}
                className={`w-full rounded-lg border p-3 text-left transition ${
                  selected?.id === s.id ? 'border-brand bg-brand/5' : 'border-ink/15 bg-white hover:bg-ivory'
                }`}
              >
                <div className="font-bold text-ink">
                  {shopName(s)} <span className="text-xs font-normal text-ink/50">#{s.id}</span>
                </div>
                <div className="text-xs text-ink/60">
                  {t('misc.offerBy')}: {s.owner_name}
                </div>
              </button>
            ))}
            {shops && filtered.length === 0 && <p className="text-sm text-ink/60">{t('needs.noProduct')}</p>}
          </div>
          <div>
            <label className="label" htmlFor="owner-pin">
              {t('login.pin')}
            </label>
            <input
              id="owner-pin"
              className="field tabular text-center text-2xl tracking-[0.5em]"
              type="password"
              inputMode="numeric"
              autoComplete="off"
              maxLength={8}
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
              onKeyDown={(e) => e.key === 'Enter' && void signIn()}
            />
          </div>
        </section>
      )}

      {role === 'operator' && (
        <section className="space-y-4">
          <div>
            <label className="label" htmlFor="op-pin">
              {t('login.pin')}
            </label>
            <input
              id="op-pin"
              className="field tabular text-center text-2xl tracking-[0.5em]"
              type="password"
              inputMode="numeric"
              autoComplete="off"
              maxLength={8}
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
              onKeyDown={(e) => e.key === 'Enter' && void signIn()}
            />
          </div>
        </section>
      )}

      {role && (
        <div className="mt-5 space-y-3">
          {error && <p className="text-sm font-semibold text-red-600">{error}</p>}
          <button type="button" className="btn-accent w-full" disabled={busy} onClick={() => void signIn()}>
            {busy ? t('common.loading') : t('login.signIn')}
          </button>
          <button type="button" className="btn-ghost w-full" onClick={() => setRole(null)}>
            {t('common.cancel')}
          </button>
          <p className="text-center text-xs text-ink/50">{t('login.pinHint')}</p>
        </div>
      )}
      <footer className="mt-10 text-center text-[11px] text-ink/40">
        {t('login.footer')}
      </footer>
    </div>
  )
}
