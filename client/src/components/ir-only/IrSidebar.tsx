import { AlertTriangle, Users, Building2, Gavel, MapPin } from 'lucide-react'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'
import { useSidebarBadges } from '../../hooks/useSidebarBadges'

const nav: (NavItem | NavGroup)[] = [
  { to: '/app/ir', icon: AlertTriangle, label: 'Incidents' },
  { to: '/app/employees', icon: Users, label: 'Employees' },
  { to: '/app/locations', icon: MapPin, label: 'Locations' },
  { to: '/app/discipline', icon: Gavel, label: 'Performance Action', feature: 'discipline' },
  { to: '/app/company', icon: Building2, label: 'Company' },
]

/**
 * Slim sidebar for Matcha Cap self-serve tenants (signup_source =
 * ir_only_self_serve). Bundle: Incidents + Employees + Discipline +
 * Company. No compliance, policies, ER Copilot, or Matcha Work links —
 * only what the Cap subscription includes.
 */
export default function IrSidebar() {
  const { me, loading, hasFeature } = useMe()
  const { badges, markSeen } = useSidebarBadges()

  const items: (NavItem | NavGroup)[] = nav
    .filter((item) => {
      if ('items' in item) return true
      return !item.feature || hasFeature(item.feature)
    })
    .map((item) => {
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
