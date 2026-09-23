import TenantSidebar from '../../components/sidebars/TenantSidebar'
import { LayoutContext } from '../../layouts/LayoutContext'
import type { Props } from '../../work/components/shell/WorkSidebar/types'

/**
 * /ops renders the SAME rail as /app — the tenant sidebar with its Matcha | Ops
 * switch, opened on the Ops side because the URL is under /ops. WorkLayout
 * owns open/collapsed state (`mw-sidebar`); this maps it onto the
 * LayoutContext SidebarShell reads, and sizes the rail the way AppLayout does.
 */
export default function OpsWorkspaceSidebar({ open, onToggle }: Props) {
  const setSidebarCollapsed = (collapsed: boolean) => {
    if (collapsed === open) onToggle()
  }
  return (
    <LayoutContext.Provider value={{ sidebarCollapsed: !open, setSidebarCollapsed }}>
      <div className={`h-full shrink-0 overflow-hidden transition-[width] duration-200 ease-in-out ${open ? 'w-60' : 'w-14'}`}>
        <TenantSidebar />
      </div>
    </LayoutContext.Provider>
  )
}
