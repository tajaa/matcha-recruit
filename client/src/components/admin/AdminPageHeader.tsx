import { useContext, type ReactNode } from 'react'
import { AdminPageContext } from './AdminPageContext'

type AdminPageHeaderProps = {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
}

export function AdminPageTitle({ children }: { children: ReactNode }) {
  const embedded = useContext(AdminPageContext)
  const Heading = embedded ? 'h2' : 'h1'
  return <Heading className={`flex flex-wrap items-center gap-2 font-semibold text-zinc-100 ${embedded ? 'text-sm' : 'text-2xl tracking-tight'}`}>{children}</Heading>
}

export function AdminPageHeader({ title, description, actions }: AdminPageHeaderProps) {
  const embedded = useContext(AdminPageContext)
  return (
    <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 flex-1 basis-64">
        <AdminPageTitle>{title}</AdminPageTitle>
        {description && <div className={`mt-2 leading-relaxed text-zinc-500 ${embedded ? 'text-xs' : 'text-sm'}`}>{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}
