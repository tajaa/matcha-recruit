import { Routes, Route, Outlet, Navigate, useLocation } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import WorkLayout from '../layout/WorkLayout'
import WerkLiteHome from '../pages/WerkLiteHome'
import WerkLiteLogin from '../pages/WerkLiteLogin'
import ChannelView from '../pages/ChannelView'
import ChannelBrowse from '../pages/ChannelBrowse'
import ChannelJoinByInvite from '../pages/ChannelJoinByInvite'
import BoardView from '../pages/BoardView'
import { FeatureGate } from '../../components/shared/FeatureGate'
import { WorkSurfaceProvider } from './WorkSurfaceContext'
import { useMe } from '../../hooks/useMe'

// Auth gate for the werk-lite surface. An unauthenticated visitor is sent to the
// DEDICATED werk-lite login — not the main /login, which role-routes an employee
// to /portal. Whole-company access: any signed-in user passes; the FeatureGate
// below enforces the `werk_lite` company entitlement (admins + employees alike,
// since /auth/me carries company enabled_features for both roles).
function WerkLiteAuthGuard() {
  const { me, loading, authFailed } = useMe()
  const location = useLocation()
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950">
        <Loader2 className="animate-spin text-zinc-600" size={24} />
      </div>
    )
  }
  // authFailed, not `!me`: useMe reports a null user for ANY /auth/me failure,
  // so redirecting on that would bounce a signed-in user to the login page over
  // a transient 502. Same fix as AppLayout / RequireRole.
  if (authFailed) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/werk-lite/login?next=${next}`} replace />
  }
  if (!me) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-sm text-zinc-500">
        Could not verify your session. Check your connection and reload.
      </div>
    )
  }
  return <Outlet />
}

// Werk Lite — a stripped business work-chat surface (channels + calls + boards
// only), served at /werk-lite with its own login. Shares page components with
// the /work + /werk trees; the surface value flips branding + nav base paths.
// Company-wide (not admin-only); Boards additionally need `matcha_work`.
export default function WerkLiteRoutes() {
  return (
    <WorkSurfaceProvider value="werk-lite">
      <Routes>
        <Route path="login" element={<WerkLiteLogin />} />
        <Route element={<WerkLiteAuthGuard />}>
          <Route element={<WorkLayout />}>
            <Route
              element={
                <FeatureGate feature="werk_lite" label="Werk Lite">
                  <Outlet />
                </FeatureGate>
              }
            >
              <Route index element={<WerkLiteHome />} />
              <Route path="channels" element={<ChannelBrowse />} />
              <Route path="channels/join/:code" element={<ChannelJoinByInvite />} />
              <Route path="channels/:channelId" element={<ChannelView />} />
              <Route path="boards/:projectId" element={<BoardView />} />
            </Route>
          </Route>
        </Route>
      </Routes>
    </WorkSurfaceProvider>
  )
}
