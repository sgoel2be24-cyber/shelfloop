import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { clearToken } from '../api/client'
import { getSession, storeSession } from '../api/sessionStore'
import type { Role } from '../api/types'

export interface SessionInfo {
  token: string
  role: Role
  shopId: number | null
  shopName: string
}

interface SessionCtx {
  session: SessionInfo | null
  login: (info: SessionInfo) => void
  logout: () => void
}

const SessionContext = createContext<SessionCtx | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(getSession)
  const login = useCallback((info: SessionInfo) => {
    storeSession(info)
    setSession(info)
  }, [])
  const logout = useCallback(() => {
    clearToken()
    setSession(null)
  }, [])
  const value = useMemo(() => ({ session, login, logout }), [session, login, logout])
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionCtx {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used inside SessionProvider')
  return ctx
}
