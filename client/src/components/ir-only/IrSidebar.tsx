import { useState } from 'react'
import { AlertTriangle, BookOpen, Building2, ClipboardList, FileText, TrendingUp, Users } from 'lucide-react'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'
import { useSidebarBadges } from '../../hooks/useSidebarBadges'
import EssentialsUpgradePanel from './EssentialsUpgradePanel'

const nav: (NavItem | NavGroup)[] = [
  { to: '/app/ir', icon: AlertTriangle, label: 'Incidents' },
  { to: '/app/ir/risk-insights', icon: TrendingUp, label: 'Risk Insights' },
  { to: '/app/ir/osha', icon: ClipboardList, label: 'OSHA Logs', feature: 'osha_logs' },
  { to: '/app/handbooks', icon: FileText, label: 'Handbooks' },
  { to: '/app/resources', icon: BookOpen, label: 'Resources' },
  { to: '/app/company', icon: Building2, label: 'Company' },
  { to: '/app/employees', icon: Users, label: 'Employees', feature: 'employees' },
  // { to: '/app', icon: LayoutDashboard, label: 'Command Center' },
  // { to: '/app/ask-expert', icon: MessageCircleQuestion, label: 'Ask an Expert' },
  // { to: '/app/training', icon: GraduationCap, label: 'Training', feature: 'training' },
  // { to: '/app/compliance-calendar', icon: CalendarDays, label: 'Compliance Calendar' },
  // { to: '/app/locations', icon: MapPin, label: 'Locations' },
]

// Nav entries Essentials swaps to locked upgrade carrots. Lock variants drop
// the `feature:` key on purpose — SidebarShell hides feature-gated items, and
// these must stay visible to sell the Essentials → Lite upgrade.
const ESSENTIALS_LOCKED = new Set(['/app/ir/osha', '/app/employees'])

export default function IrSidebar() {
  const { me, loading } = useMe()
  const { badges, markSeen } = useSidebarBadges()
  const isEssentials = me?.profile?.signup_source === 'matcha_lite_essentials'
  // Bumped when a locked carrot is clicked — pulses the upgrade panel below.
  const [upgradeNudge, setUpgradeNudge] = useState(0)

  const items: (NavItem | NavGroup)[] = nav.map((item) => {
    if ('items' in item) return item
    if (item.to === '/app/ir') {
      return { ...item, badge: badges.ir || undefined, onSeen: () => markSeen('ir') }
    }
    if (isEssentials && ESSENTIALS_LOCKED.has(item.to)) {
      const { feature: _feature, ...rest } = item
      return { ...rest, locked: true, onLockedClick: () => setUpgradeNudge((n) => n + 1) }
    }
    return item
  })

  const footerName = me?.profile?.company_name

  return (
    <SidebarShell
      logoTo="/app/ir"
      logoLabel="Matcha Lite"
      nav={loading ? [] : items}
      upgradeFooter={
        isEssentials ? (
          <EssentialsUpgradePanel headcount={me?.profile?.headcount ?? 0} nudge={upgradeNudge} />
        ) : undefined
      }
      user={footerName ? {
        name: footerName,
        avatarUrl: me?.user?.avatar_url,
        settingsTo: '/app/settings',
      } : undefined}
    />
  )
}
