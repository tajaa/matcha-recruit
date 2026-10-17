import type { ReactNode } from 'react'

type AdminPageHeaderProps = {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
}

export function AdminPageTitle({ children }: { children: ReactNode }) {
  return <h1 className="flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight text-zinc-100">{children}</h1>
}

export function AdminPageHeader({ title, description, actions }: AdminPageHeaderProps) {
  return (
    <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 flex-1 basis-64">
        <AdminPageTitle>{title}</AdminPageTitle>
        {description && <div className="mt-2 text-sm leading-relaxed text-zinc-500">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}
