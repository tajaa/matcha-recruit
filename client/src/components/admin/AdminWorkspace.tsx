import type { ComponentProps, ReactNode } from 'react'
import { AdminPageHeader } from './AdminPageHeader'

type AdminWorkspaceProps = ComponentProps<typeof AdminPageHeader> & {
  children: ReactNode
  direction?: 'row' | 'column'
}

// Tools share Settings' open canvas and normal page scroll. List/detail tools
// keep their side-by-side organization without an extra dark console frame.
export function AdminWorkspace({ children, direction = 'column', ...header }: AdminWorkspaceProps) {
  return (
    <div>
      <AdminPageHeader {...header} />
      <div className={`flex min-w-0 gap-6 ${direction === 'column' ? 'flex-col' : 'flex-col md:flex-row'}`}>
        {children}
      </div>
    </div>
  )
}
