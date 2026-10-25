import { Navigate, Outlet } from 'react-router-dom'
import { useSession } from '../state/Session'
import type { Role } from '../api/types'

/** Route guard: requires a session with the given role, else redirects. */
export function RequireRole({ role }: { role: Role }) {
  const { session } = useSession()
  if (!session) return <Navigate to="/login" replace />
  if (session.role !== role) {
    return <Navigate to={session.role === 'owner' ? '/today' : '/operator'} replace />
  }
  return <Outlet />
}
