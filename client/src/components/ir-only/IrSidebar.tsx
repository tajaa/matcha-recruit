import { AlertTriangle, Users, Building2, Gavel, MapPin, BookOpen, CalendarDays } from 'lucide-react'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'
import { useSidebarBadges } from '../../hooks/useSidebarBadges'

const nav: (NavItem | NavGroup)[] = [
  { to: '/app/ir', icon: AlertTriangle, label: 'Incidents' },
  { to: '/app/employees', icon: Users, label: 'Employees', feature: 'employees' },
  { to: '/app/locations', icon: MapPin, label: 'Locations' },
  { to: '/app/compliance-calendar', icon: CalendarDays, label: 'Compliance Calendar' },
  { to: '/app/discipline', icon: Gavel, label: 'Performance Action', feature: 'discipline' },
  { to: '/app/resources', icon: BookOpen, label: 'Resources' },
  { to: '/app/company', icon: Building2, label: 'Company' },
]

/**
 * Slim sidebar for Matcha Cap / Matcha Lite tenants. ir_only_self_serve
 * gets Incidents + Employees + Discipline + Company. matcha_lite gets a
 * narrower Incidents + Locations + Company set since Employees and
 * Discipline aren't in the bundle. Per-item feature gates handle both.
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
