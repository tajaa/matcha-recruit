import { useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Menu, X, Loader2 } from 'lucide-react'
import PortalSidebar from '../../components/portal/PortalSidebar'
import { useMe } from '../../hooks/useMe'

export default function PortalLayout() {
  const { me, loading } = useMe()
  const { pathname } = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  useEffect(() => {
    setMobileMenuOpen(false)
  }, [pathname])

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-zinc-950 text-zinc-500">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    )
  }

  if (!me) {
    return <Navigate to={`/login?next=${encodeURIComponent(pathname)}`} replace />
  }

  // Employees only — others get redirected to their tenant root.
  const role = me.user?.role
  if (role && role !== 'employee') {
    const fallback =
      role === 'admin' ? '/admin' :
      role === 'broker' ? '/broker' :
      role === 'individual' ? '/werk' :
      '/app'
    return <Navigate to={fallback} replace />
  }

  return (
    <div className="h-screen bg-zinc-950 flex flex-col overflow-hidden">
      <header className="md:hidden flex items-center gap-2 px-3 py-3 border-b border-zinc-800 shrink-0">
        <button
          onClick={() => setMobileMenuOpen(true)}
          className="text-zinc-400 hover:text-white p-1"
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="text-sm font-medium text-white">Matcha Portal</span>
      </header>

      <div className="flex flex-1 min-h-0 relative">
        {mobileMenuOpen && (
          <div
            className="fixed inset-0 bg-black/60 z-50 md:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />
        )}

        <div className="hidden md:flex shrink-0">
          <PortalSidebar />
        </div>

        <div
          className={`fixed inset-y-0 left-0 z-50 transform transition-transform duration-200 md:hidden ${
            mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          <PortalSidebar />
          <button
            onClick={() => setMobileMenuOpen(false)}
            className="absolute top-4 -right-12 text-zinc-400 hover:text-white p-2"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        <main className="flex-1 min-w-0 overflow-auto px-6 py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
