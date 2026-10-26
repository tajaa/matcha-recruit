import { useLayoutEffect, useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { logoutSession } from '../api/client'
import { GUMMFIT_ADMIN_PATH } from '../api/authPaths'
import { useMe } from '../hooks/useMe'
import { AdminButton } from '../components/admin/AdminUI'

/** Gummfit's staff console shares the existing admin tools and auth realm. */
export default function GummfitAdminLayout() {
  const { me } = useMe()
  const [loggingOut, setLoggingOut] = useState(false)

  useLayoutEffect(() => {
    const root = document.documentElement
    const theme = root.getAttribute('data-theme')
    const shell = root.getAttribute('data-app-shell-bg')
    root.removeAttribute('data-theme')
    root.setAttribute('data-app-shell-bg', 'admin')
    return () => {
      if (theme === null) root.removeAttribute('data-theme')
      else root.setAttribute('data-theme', theme)
      if (shell === null) root.removeAttribute('data-app-shell-bg')
      else root.setAttribute('data-app-shell-bg', shell)
    }
  }, [])

  function signOut() {
    if (loggingOut) return
    setLoggingOut(true)
    void logoutSession()
  }

  return (
    <div className="admin-shell min-h-screen">
      <header className="border-b border-white/5 px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4">
          <Link to={GUMMFIT_ADMIN_PATH} className="text-lg tracking-tight text-zinc-100">Gummfit <span className="text-sm text-zinc-500">Admin</span></Link>
          <div className="flex flex-wrap items-center gap-4 text-xs text-zinc-400">
            <span>{me?.user.email}</span>
            <Link to="/cappe" className="hover:text-zinc-100">View Gummfit</Link>
            <AdminButton variant="ghost" size="sm" disabled={loggingOut} onClick={signOut}>{loggingOut ? 'Signing out…' : 'Sign out'}</AdminButton>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full min-w-0 max-w-6xl px-4 py-6 sm:px-6">
        <nav aria-label="Gummfit admin" className="mb-6 flex gap-5 border-b border-white/5 pb-3 text-sm">
          <NavLink end to={GUMMFIT_ADMIN_PATH} className={({ isActive }) => isActive ? 'text-zinc-100' : 'text-zinc-500 hover:text-zinc-200'}>Administration</NavLink>
          <NavLink to={`${GUMMFIT_ADMIN_PATH}/models`} className={({ isActive }) => isActive ? 'text-zinc-100' : 'text-zinc-500 hover:text-zinc-200'}>AI models</NavLink>
        </nav>
        <Outlet />
      </main>
    </div>
  )
}
