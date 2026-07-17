import { BadgeCheck, Building2, CalendarClock, FileText, Shield, Users, Zap } from 'lucide-react'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'

// Standalone Matcha Compliance product sidebar. A paid matcha_compliance tenant
// has `compliance` on (flipped by the Stripe webhook) plus the four-pillar
// bundle granted by the matcha_compliance TIER_REQUIRED overlay: policy
// management and credentialing (with the employee roster it needs). Each
// pillar nav item is feature-gated so it only renders when the overlay flag
// is on — the pending shell handles the unpaid state upstream.
const nav: (NavItem | NavGroup)[] = [
  { to: '/app/compliance', icon: Shield, label: 'Compliance' },
  { to: '/app/compliance-calendar', icon: CalendarClock, label: 'Compliance Calendar' },
  { to: '/app/policies', icon: FileText, label: 'Policy Management', feature: 'policies' },
  { to: '/app/credential-templates', icon: BadgeCheck, label: 'Credentialing', feature: 'credential_templates' },
  { to: '/app/employees', icon: Users, label: 'Employees', feature: 'employees' },
  { to: '/app/company', icon: Building2, label: 'Company' },
  { to: '/compliance/onboarding', icon: Zap, label: 'Compliance Setup' },
]

export default function ComplianceSidebar() {
  const { me, loading } = useMe()
  const footerName = me?.profile?.company_name

  return (
    <SidebarShell
      logoTo="/app/compliance"
      logoLabel="Matcha Compliance"
      nav={loading ? [] : nav}
      user={footerName ? {
        name: footerName,
        avatarUrl: me?.user?.avatar_url,
        settingsTo: '/app/settings',
      } : undefined}
    />
  )
}
