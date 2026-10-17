import type { ComponentProps, ReactNode } from 'react'
import { AdminPageHeader } from './AdminPageHeader'

type AdminWorkspaceProps = ComponentProps<typeof AdminPageHeader> & {
  children: ReactNode
  direction?: 'row' | 'column'
}

// List/detail tools share the same header as Settings, with a bounded panel
// below. Short windows and phones can scroll the page instead of clipping it.
export function AdminWorkspace({ children, direction = 'column', ...header }: AdminWorkspaceProps) {
  return (
    <div>
      <AdminPageHeader {...header} />
      <div className={`flex h-[calc(100dvh-18rem)] min-h-[32rem] overflow-auto rounded-lg border border-zinc-800 bg-zinc-900/50 ${direction === 'column' ? 'flex-col' : 'flex-col md:flex-row'}`}>
        {children}
      </div>
    </div>
  )
}
