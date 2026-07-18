import { Routes, Route, Outlet, Navigate, useLocation } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import WorkLayout from '../layouts/WorkLayout'
import WerkLiteHome from '../pages/work/WerkLiteHome'
import WerkLiteLogin from '../pages/work/WerkLiteLogin'
import ChannelView from '../pages/work/ChannelView'
import ChannelBrowse from '../pages/work/ChannelBrowse'
import ChannelJoinByInvite from '../pages/work/ChannelJoinByInvite'
import BoardView from '../pages/work/BoardView'
import { FeatureGate } from '../components/shared/FeatureGate'
import { WorkSurfaceProvider } from './WorkSurfaceContext'
import { useMe } from '../hooks/useMe'

// Auth gate for the werk-lite surface. An unauthenticated visitor is sent to the
// DEDICATED werk-lite login — not the main /login, which role-routes an employee
// to /portal. Whole-company access: any signed-in user passes; the FeatureGate
// below enforces the `werk_lite` company entitlement (admins + employees alike,
// since /auth/me carries company enabled_features for both roles).
function WerkLiteAuthGuard() {
  const { me, loading } = useMe()
  const location = useLocation()
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950">
        <Loader2 className="animate-spin text-zinc-600" size={24} />
      </div>
    )
  }
  if (!me) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/werk-lite/login?next=${next}`} replace />
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
