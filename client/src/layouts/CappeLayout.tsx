import { useEffect } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useCappeMe } from '../hooks/useCappeMe'
import { getCappeToken } from '../api/cappeClient'
import CappeSidebar from '../components/CappeSidebar'

// Authenticated Cappe shell. Independent of TenantSidebar — Cappe is its own
// product. Redirects to /cappe/login when there is no live Cappe session.
export default function CappeLayout() {
  const { account, loading } = useCappeMe()
  const navigate = useNavigate()

  useEffect(() => {
    if (!getCappeToken()) {
      navigate('/cappe/login', { replace: true })
      return
    }
    if (!loading && !account) {
      navigate('/cappe/login', { replace: true })
    }
  }, [loading, account, navigate])

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
