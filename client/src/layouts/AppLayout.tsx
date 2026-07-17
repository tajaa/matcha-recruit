import { useState, useEffect, type ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { useMe } from '../hooks/useMe'
import { LayoutContext } from './LayoutContext'
import HelpAssistant from '../components/help/HelpAssistant'
import { resolvePageHelp } from '../data/pageHelp'

const PERSONAL_ALLOWED = new Set(['/app/settings'])

export default function AppLayout({ sidebar, variant }: { sidebar: ReactNode; logoLabel?: string; variant?: 'admin' }) {
  const { loading, isPersonal } = useMe()
  const { pathname } = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    localStorage.getItem('sidebar_collapsed') === 'true'
  )
  const isAdmin = variant === 'admin'

  useEffect(() => {
    document.documentElement.setAttribute('data-app-shell-bg', isAdmin ? 'admin' : 'true')
    return () => document.documentElement.removeAttribute('data-app-shell-bg')
  }, [isAdmin])

  useEffect(() => {
    setMobileMenuOpen(false)
  }, [pathname])

  useEffect(() => {
    localStorage.setItem('sidebar_collapsed', String(sidebarCollapsed))
  }, [sidebarCollapsed])

  if (!loading && isPersonal && !PERSONAL_ALLOWED.has(pathname)) {
    return <Navigate to="/werk" replace />
  }

  return (
    <LayoutContext.Provider value={{ sidebarCollapsed, setSidebarCollapsed }}>
      <div className={isAdmin ? 'min-h-screen bg-gradient-to-b from-zinc-700 to-zinc-900' : 'min-h-screen bg-vsc-bg'}>

        {/* No top bar: it spent 56px on a logo, a page title every page already
            prints as its own <h1>, and an avatar — all of which the sidebar can
            hold. The rail is the only chrome now. */}

        {/* Mobile: the rail is off-canvas, so the drawer needs a trigger. */}
        <button
          onClick={() => setMobileMenuOpen(true)}
          aria-label="Open menu"
          className="fixed left-3 top-3 z-30 rounded-md border border-zinc-800/80 bg-zinc-950/80 p-2 text-zinc-400 backdrop-blur transition-colors hover:text-zinc-100 md:hidden"
        >
          <Menu className="h-[18px] w-[18px]" strokeWidth={1.6} />
        </button>

        {/* Mobile sidebar backdrop */}
        {mobileMenuOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/60 md:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />
        )}

        {/* Sidebar — full height now that nothing sits above it.
            Mobile: full-width overlay (translate).
            Desktop: icon-only when collapsed (width transition). */}
        <div className={`fixed bottom-0 left-0 top-0 z-50 w-60 overflow-hidden transition-all duration-200 ease-in-out
          ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}
          md:translate-x-0 ${sidebarCollapsed ? 'md:w-14' : 'md:w-60'}
        `}>
          {sidebar}
          <button
            onClick={() => setMobileMenuOpen(false)}
            aria-label="Close menu"
            className="absolute -right-12 top-4 p-2 text-zinc-400 hover:text-white md:hidden"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        {/* Main content — pt-16 on mobile clears the floating menu trigger. */}
        <main className={`p-4 pt-16 transition-[margin] duration-200 ease-in-out md:p-8 md:pt-8 ${
          sidebarCollapsed ? 'md:ml-14' : 'md:ml-60'
        }`}>
          <Outlet />
        </main>

        {/* Floating per-page help guide — only on pages with a pageHelp entry.
            key resets chat state when the user navigates to another page. */}
        {(() => {
          const help = resolvePageHelp(pathname)
          return help ? <HelpAssistant key={help.match} pageHelp={help} /> : null
        })()}

      </div>
    </LayoutContext.Provider>
  )
}
