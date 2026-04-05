import { useState, useEffect, type ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { useMe } from '../hooks/useMe'

const PERSONAL_ALLOWED = new Set(['/app/settings'])

export default function AppLayout({ sidebar }: { sidebar: ReactNode }) {
  const { loading, isPersonal } = useMe()
  const { pathname } = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [pathname])

  // Block personal accounts from platform routes (they only have Matcha Work)
  if (!loading && isPersonal && !PERSONAL_ALLOWED.has(pathname)) {
    return <Navigate to="/work" replace />
  }

  return (
    <div className="min-h-screen bg-vsc-bg flex flex-col md:block">
      {/* Mobile Header */}
      <header className="md:hidden flex items-center justify-between p-4 bg-[#2d2d30] border-b border-vsc-border/30 sticky top-0 z-40">
        <div className="font-semibold text-zinc-100 tracking-tight">Matcha</div>
        <button 
          onClick={() => setMobileMenuOpen(true)}
          className="text-zinc-400 hover:text-white p-1"
        >
          <Menu className="h-5 w-5" />
        </button>
      </header>

      {/* Mobile Sidebar Overlay */}
      {mobileMenuOpen && (
        <div 
          className="fixed inset-0 bg-black/60 z-50 md:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar Container */}
      <div className={`fixed inset-y-0 left-0 z-50 w-56 transform transition-transform duration-200 ease-in-out md:translate-x-0 flex ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex-1 w-full overflow-hidden">
          {sidebar}
        </div>
        <button 
          onClick={() => setMobileMenuOpen(false)}
          className="md:hidden absolute top-4 -right-12 text-zinc-400 hover:text-white p-2"
        >
          <X className="h-6 w-6" />
        </button>
      </div>

      <main className="flex-1 md:ml-56 p-4 md:p-8">
        <Outlet />
      </main>
    </div>
  )
}
