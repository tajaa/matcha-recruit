import { useState, useEffect, type ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Menu, X, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useMe } from '../hooks/useMe'
import { Logo } from '../components/ui'
import { LayoutContext } from './LayoutContext'

const PERSONAL_ALLOWED = new Set(['/app/settings'])

const PAGE_TITLES: Record<string, string> = {
  '': 'Command Center',
  'company': 'Company Settings',
  'employees': 'Employees',
  'onboarding': 'Onboarding',
  'er-copilot': 'ER Copilot',
  'compliance': 'Compliance',
  'compliance-calendar': 'Compliance Calendar',
  'ir': 'Incidents',
  'locations': 'Locations',
  'escalated-queries': 'Escalated Queries',
  'accommodations': 'Accommodations',
  'discipline': 'Performance Action',
  'discipline-settings': 'Performance Settings',
  'policies': 'Policies',
  'handbooks': 'Handbooks',
  'handbook': 'Handbooks',
  'training': 'Training',
  'ask-expert': 'Ask an Expert',
  'risk-assessment': 'Risk Assessment',
  'credential-templates': 'Credential Templates',
  'resources': 'Resources',
  'inbox': 'Inbox',
  'notifications': 'Notifications',
  'settings': 'Settings',
}

function getPageTitle(pathname: string): string {
  const seg = pathname.replace(/^\/app\/?/, '').split('/')[0]
  return PAGE_TITLES[seg] ?? 'Matcha'
}

function getInitials(name: string | null | undefined, email: string | undefined): string {
  if (name) {
    const parts = name.trim().split(/\s+/)
    return parts.length >= 2
      ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
      : parts[0].slice(0, 2).toUpperCase()
  }
  return (email?.[0] ?? 'M').toUpperCase()
}

export default function AppLayout({ sidebar, logoLabel }: { sidebar: ReactNode; logoLabel?: string }) {
  const { loading, isPersonal, me } = useMe()
  const { pathname } = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    localStorage.getItem('sidebar_collapsed') === 'true'
  )

  useEffect(() => {
    setMobileMenuOpen(false)
  }, [pathname])

  useEffect(() => {
    localStorage.setItem('sidebar_collapsed', String(sidebarCollapsed))
  }, [sidebarCollapsed])

  if (!loading && isPersonal && !PERSONAL_ALLOWED.has(pathname)) {
    return <Navigate to="/werk" replace />
  }

  const pageTitle = getPageTitle(pathname)
  const initials = getInitials(me?.profile?.name, me?.user?.email)
  const avatarUrl = me?.user?.avatar_url

  const src = me?.profile?.signup_source
  const derivedLabel = logoLabel ?? (
    src === 'matcha_lite' || src === 'ir_only_self_serve' || src === 'ir_only'
      ? 'Matcha Lite'
      : 'Matcha'
  )

  return (
    <LayoutContext.Provider value={{ hasTopNav: true, sidebarCollapsed }}>
      <div className="min-h-screen bg-vsc-bg">

        {/* Full-width top navbar */}
        <header className="fixed top-0 left-0 right-0 h-14 bg-[#141416] border-b border-vsc-border/30 flex items-center px-4 z-40 gap-3">
          {/* Desktop: collapse toggle */}
          <button
            onClick={() => setSidebarCollapsed(v => !v)}
            className="hidden md:flex text-zinc-400 hover:text-white p-1.5 rounded-md hover:bg-zinc-800/40 transition-colors"
          >
            {sidebarCollapsed
              ? <PanelLeftOpen className="h-[18px] w-[18px]" strokeWidth={1.6} />
              : <PanelLeftClose className="h-[18px] w-[18px]" strokeWidth={1.6} />
            }
          </button>

          {/* Mobile: hamburger */}
          <button
            onClick={() => setMobileMenuOpen(true)}
            className="md:hidden text-zinc-400 hover:text-white p-1.5 rounded-md hover:bg-zinc-800/40 transition-colors"
          >
            <Menu className="h-[18px] w-[18px]" strokeWidth={1.6} />
          </button>

          <Logo to="/app" label={derivedLabel} />

          <div className="flex-1" />

          <span className="hidden md:block text-[13px] text-zinc-500 font-medium">{pageTitle}</span>

          <div className="flex-1" />

          <div className="flex items-center gap-2.5">
            {avatarUrl ? (
              <img src={avatarUrl} alt="" className="w-7 h-7 rounded-full object-cover" />
            ) : (
              <div className="w-7 h-7 rounded-full bg-emerald-700 flex items-center justify-center text-[11px] font-semibold text-white select-none">
                {initials}
              </div>
            )}
            {me?.profile?.name && (
              <span className="hidden md:block text-sm text-zinc-400 leading-none">{me.profile.name}</span>
            )}
          </div>
        </header>

        {/* Mobile sidebar backdrop */}
        {mobileMenuOpen && (
          <div
            className="fixed inset-0 top-14 bg-black/60 z-40 md:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />
        )}

        {/* Sidebar — starts below navbar.
            Mobile: full-width overlay (translate).
            Desktop: icon-only when collapsed (width transition). */}
        <div className={`fixed top-14 left-0 bottom-0 z-50 overflow-hidden transition-all duration-200 ease-in-out
          w-56
          ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}
          md:translate-x-0 ${sidebarCollapsed ? 'md:w-14' : 'md:w-56'}
        `}>
          {sidebar}
          <button
            onClick={() => setMobileMenuOpen(false)}
            className="md:hidden absolute top-4 -right-12 text-zinc-400 hover:text-white p-2"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        {/* Main content */}
        <main className={`mt-14 p-4 md:p-8 transition-[margin] duration-200 ease-in-out ${
          sidebarCollapsed ? 'md:ml-14' : 'md:ml-56'
        }`}>
          <Outlet />
        </main>

      </div>
    </LayoutContext.Provider>
  )
}
