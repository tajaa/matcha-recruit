import type { NavGroup, NavItem } from './SidebarShell'

// The Matcha | Ops switch's split: a row belongs to the Ops side when it leads
// into /ops. Kept out of SidebarShell.tsx so that file exports only components.

export type Workspace = 'matcha' | 'ops'

export function isOpsPath(path: string): boolean {
  return path === '/ops' || path.startsWith('/ops/')
}

/** Rows that lead into /ops belong to the Ops side of the switch. */
export function withoutOpsRows(nav: (NavItem | NavGroup)[]): (NavItem | NavGroup)[] {
  return nav.reduce<(NavItem | NavGroup)[]>((out, item) => {
    if ('items' in item) {
      const items = item.items.filter((child) => !isOpsPath(child.to))
      if (items.length > 0) out.push({ ...item, items })
    } else if (!isOpsPath(item.to)) {
      out.push(item)
    }
    return out
  }, [])
}
