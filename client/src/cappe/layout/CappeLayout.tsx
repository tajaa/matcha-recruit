import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Loader2, Menu, X } from 'lucide-react'
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

  // Phone-width navigation drawer. Stored as the path it was opened on, so
  // following any link closes it without an effect having to reset state.
  const [navOpenAt, setNavOpenAt] = useState<string | null>(null)
  const navOpen = navOpenAt === location.pathname

  useEffect(() => {
    if (!navOpen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setNavOpenAt(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navOpen])

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
    <div className="flex h-dvh flex-col overflow-hidden bg-zinc-950 text-zinc-100 md:flex-row">
      {/* Below md the sidebar is a drawer; this bar is how you reach it. */}
      <header className="flex shrink-0 items-center gap-3 border-b border-zinc-800 bg-zinc-900 px-4 py-3 md:hidden">
        <button
          type="button"
          onClick={() => setNavOpenAt(navOpen ? null : location.pathname)}
          aria-label={navOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={navOpen}
          aria-controls="cappe-sidebar"
          className="rounded-lg p-1.5 text-zinc-300 hover:bg-zinc-800"
        >
          {navOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
        <span className="text-base font-semibold tracking-tight text-zinc-50">
          {account.account_type === 'creator' ? 'Gummfit Creators' : 'Gummfit'}
        </span>
      </header>
      <CappeSidebar account={account} open={navOpen} onClose={() => setNavOpenAt(null)} />
      <main className="min-w-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
