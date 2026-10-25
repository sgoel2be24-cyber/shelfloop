import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireRole } from './components/Guard'
import Login from './pages/Login'
import OwnerShell from './pages/owner/OwnerShell'
import OperatorShell from './pages/operator/OperatorShell'
import { useSession } from './state/Session'

// Route-level code splitting: the operator workspace (graph, dashboards) is the
// heavy half of the bundle and owners rarely touch it.
const Today = lazy(() => import('./pages/owner/Today'))
const Stock = lazy(() => import('./pages/owner/Stock'))
const Needs = lazy(() => import('./pages/owner/Needs'))
const Approvals = lazy(() => import('./pages/owner/Approvals'))
const Overview = lazy(() => import('./pages/operator/Overview'))
const Planning = lazy(() => import('./pages/operator/Planning'))
const GraphPage = lazy(() => import('./pages/operator/GraphPage'))
const Rehearsal = lazy(() => import('./pages/operator/Rehearsal'))
const Evidence = lazy(() => import('./pages/operator/Evidence'))

function HomeRedirect() {
  const { session } = useSession()
  if (!session) return <Navigate to="/login" replace />
  return <Navigate to={session.role === 'owner' ? '/today' : '/operator'} replace />
}

function RouteFallback() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <div className="flex items-center gap-2 text-sm font-semibold text-ink/50">
        <span className="h-2.5 w-2.5 animate-bounce rounded-full bg-accent [animation-delay:-0.2s]" />
        <span className="h-2.5 w-2.5 animate-bounce rounded-full bg-brand [animation-delay:-0.1s]" />
        <span className="h-2.5 w-2.5 animate-bounce rounded-full bg-accent" />
      </div>
    </div>
  )
}

export default function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route element={<RequireRole role="owner" />}>
          <Route element={<OwnerShell />}>
            <Route path="/today" element={<Today />} />
            <Route path="/stock" element={<Stock />} />
            <Route path="/needs" element={<Needs />} />
            <Route path="/approvals" element={<Approvals />} />
          </Route>
        </Route>

        <Route element={<RequireRole role="operator" />}>
          <Route element={<OperatorShell />}>
            <Route path="/operator" element={<Overview />} />
            <Route path="/operator/planning" element={<Planning />} />
            <Route path="/operator/graph" element={<GraphPage />} />
            <Route path="/operator/rehearsal" element={<Rehearsal />} />
            <Route path="/operator/evidence" element={<Evidence />} />
          </Route>
        </Route>

        <Route path="*" element={<HomeRedirect />} />
      </Routes>
    </Suspense>
  )
}
