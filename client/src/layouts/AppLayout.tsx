import type { ReactNode } from 'react'
import { Outlet } from 'react-router-dom'

export default function AppLayout({ sidebar }: { sidebar: ReactNode }) {
  return (
    <div className="min-h-screen bg-zinc-950">
      {sidebar}
      <main className="ml-56 p-8">
        <Outlet />
      </main>
    </div>
  )
}
