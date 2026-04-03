import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useMe } from '../hooks/useMe'

const PERSONAL_ALLOWED = new Set(['/app/settings'])

export default function AppLayout({ sidebar }: { sidebar: ReactNode }) {
  const { loading, isPersonal } = useMe()
  const { pathname } = useLocation()

  // Block personal accounts from platform routes (they only have Matcha Work)
  if (!loading && isPersonal && !PERSONAL_ALLOWED.has(pathname)) {
    return <Navigate to="/work" replace />
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      {sidebar}
      <main className="ml-56 p-8">
        <Outlet />
      </main>
    </div>
  )
}
