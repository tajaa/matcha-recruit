import { AlertTriangle, BadgeCheck, BookOpen, Building2, ClipboardList, FileText, Gavel, GraduationCap, ShieldAlert, TrendingUp, Users, Zap } from 'lucide-react'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'
import { useSidebarBadges } from '../../hooks/useSidebarBadges'

// Matcha-X (mid tier) sidebar. Lite (IR + employees + handbook generation)
// PLUS the mid-tier modules: handbook audit, training, progressive discipline,
// credentialing. Each module nav item is feature-gated so it only renders when
// the tier overlay (TIER_REQUIRED_FEATURES["matcha_x"]) has it on.
const nav: (NavItem | NavGroup)[] = [
  { to: '/app/ir', icon: AlertTriangle, label: 'Incidents' },
  { to: '/app/ir/risk-insights', icon: TrendingUp, label: 'Risk Insights' },
  { to: '/app/ir/osha', icon: ClipboardList, label: 'OSHA Logs' },
  { to: '/app/handbooks', icon: FileText, label: 'Handbooks' },
  { to: '/app/resources/handbook-audit', icon: ShieldAlert, label: 'Handbook Audit', feature: 'handbook_audit' },
  { to: '/app/training', icon: GraduationCap, label: 'Training', feature: 'training' },
  { to: '/app/discipline', icon: Gavel, label: 'Performance Action', feature: 'discipline' },
  { to: '/app/credential-templates', icon: BadgeCheck, label: 'Credentialing', feature: 'credential_templates' },
  { to: '/app/resources', icon: BookOpen, label: 'Resources' },
  { to: '/app/company', icon: Building2, label: 'Company' },
  { to: '/app/employees', icon: Users, label: 'Employees', feature: 'employees' },
  { to: '/matcha-x/onboarding', icon: Zap, label: 'Compliance Setup' },
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
