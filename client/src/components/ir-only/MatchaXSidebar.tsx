import { AlertTriangle, BookOpen, Building2, ClipboardList, FileText, ShieldAlert, TrendingUp, Users } from 'lucide-react'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'
import { useSidebarBadges } from '../../hooks/useSidebarBadges'

// Matcha-X (mid tier) sidebar. Clone of IrSidebar at strict Lite parity —
// dedicated so its nav can grow (HRIS, credential tracking) without touching
// the Lite sidebar. Keep the nav in sync with IrSidebar until the mid-tier
// modules land.
const nav: (NavItem | NavGroup)[] = [
  { to: '/app/ir', icon: AlertTriangle, label: 'Incidents' },
  { to: '/app/ir/risk-insights', icon: TrendingUp, label: 'Risk Insights' },
  { to: '/app/ir/osha', icon: ClipboardList, label: 'OSHA Logs' },
  { to: '/app/handbooks', icon: FileText, label: 'Handbooks' },
  { to: '/app/resources/handbook-audit', icon: ShieldAlert, label: 'Handbook Audit' },
  { to: '/app/resources', icon: BookOpen, label: 'Resources' },
  { to: '/app/company', icon: Building2, label: 'Company' },
  { to: '/app/employees', icon: Users, label: 'Employees', feature: 'employees' },
]

export default function MatchaXSidebar() {
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
      logoLabel="Matcha-X"
      nav={loading ? [] : items}
      user={footerName ? {
        name: footerName,
        avatarUrl: me?.user?.avatar_url,
        settingsTo: '/app/settings',
      } : undefined}
    />
  )
}
