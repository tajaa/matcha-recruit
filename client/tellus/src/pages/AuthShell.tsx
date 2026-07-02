import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

export function AuthShell({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <Link to="/tellus-app" className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-tu-dim transition hover:text-tu-text">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Tell-Us
        </Link>
        <div className="mb-6 text-center">
          <Link to="/tellus-app" className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-tu-accent text-lg font-black text-black transition hover:bg-tu-accent-soft">TU</Link>
          <h1 className="text-xl font-bold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-tu-dim">{subtitle}</p>}
        </div>
        {children}
      </div>
    </div>
  )
}
