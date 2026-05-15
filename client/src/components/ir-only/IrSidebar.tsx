import { AlertTriangle, BookOpen, TrendingUp } from 'lucide-react'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'
import { useSidebarBadges } from '../../hooks/useSidebarBadges'

const nav: (NavItem | NavGroup)[] = [
  { to: '/app/ir', icon: AlertTriangle, label: 'Incidents' },
  { to: '/app/ir/risk-insights', icon: TrendingUp, label: 'Risk Insights' },
  { to: '/app/resources', icon: BookOpen, label: 'Resources' },
  // { to: '/app', icon: LayoutDashboard, label: 'Command Center' },
  // { to: '/app/ask-expert', icon: MessageCircleQuestion, label: 'Ask an Expert' },
  // { to: '/app/handbooks', icon: FileText, label: 'Handbooks', feature: 'handbooks' },
  // { to: '/app/training', icon: GraduationCap, label: 'Training', feature: 'training' },
  // { to: '/app/compliance-calendar', icon: CalendarDays, label: 'Compliance Calendar' },
  // { to: '/app/locations', icon: MapPin, label: 'Locations' },
  // { to: '/app/employees', icon: Users, label: 'Employees', feature: 'employees' },
  // { to: '/app/company', icon: Building2, label: 'Company' },
]

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
      logoLabel="Matcha Lite"
      nav={loading ? [] : items}
      user={footerName ? {
        name: footerName,
        avatarUrl: me?.user?.avatar_url,
        settingsTo: '/app/settings',
      } : undefined}
    />
  )
}
