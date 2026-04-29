import { AlertTriangle, Users, Settings, Building2 } from 'lucide-react'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'
import { useSidebarBadges } from '../../hooks/useSidebarBadges'

const nav: (NavItem | NavGroup)[] = [
  { to: '/app/ir', icon: AlertTriangle, label: 'Incidents' },
  { to: '/app/employees', icon: Users, label: 'Employees' },
  { to: '/app/company', icon: Building2, label: 'Company' },
]

/**
 * Slim sidebar for Matcha IR self-serve tenants. No HR-ops, compliance,
 * policies, ER Copilot, or Matcha Work links — only what an IR-only
 * subscription gives access to.
 */
export default function IrSidebar() {
  const { me, loading } = useMe()
  const { badges, markSeen } = useSidebarBadges()

  const items: (NavItem | NavGroup)[] = nav.map((item) => {
    if ('items' in item) return item
    if (item.to === '/app/ir') {
      return { ...item, badge: badges.ir || undefined, onSeen: () => markSeen('ir') }
    }
    return item
  })

  const footerName = me?.profile?.company_name

  return (
    <SidebarShell
      logoTo="/app/ir"
      logoLabel="Matcha IR"
      nav={loading ? [] : items}
      user={footerName ? {
        name: footerName,
        avatarUrl: me?.user?.avatar_url,
        settingsTo: '/app/settings',
      } : undefined}
    />
  )
}
