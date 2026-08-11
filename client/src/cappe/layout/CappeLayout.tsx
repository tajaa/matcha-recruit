import { useEffect } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useCappeMe } from '../hooks/useCappeMe'
import { getCappeToken } from '../api'
import CappeSidebar from '../components/CappeSidebar'
import { creatorPaths } from '../creators/creatorPaths'

// Authenticated Cappe shell. Independent of TenantSidebar — Cappe is its own
// product. Redirects to /cappe/login when there is no live Cappe session.
export default function CappeLayout() {
  const { account, loading } = useCappeMe()
  const navigate = useNavigate()
  const location = useLocation()
  const isCreatorDashboard = location.pathname.includes('/creators/dashboard') || location.pathname.includes('/creator')
  const isBrandCreatorDashboard = location.pathname.includes('/creators/brands/dashboard')
  const loginPath = isBrandCreatorDashboard ? creatorPaths.brandLogin : isCreatorDashboard ? creatorPaths.login : '/cappe/login'

  useEffect(() => {
    if (!getCappeToken()) {
      navigate(loginPath, { replace: true })
      return
    }
    if (!loading && !account) {
      navigate(loginPath, { replace: true })
    }
  }, [loading, account, navigate, loginPath])

  if (loading || (!account && getCappeToken())) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
      </div>
    )
  }

  if (!account) return null

  return (
    <div className="flex min-h-screen bg-zinc-950 text-zinc-100">
      <CappeSidebar account={account} />
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
