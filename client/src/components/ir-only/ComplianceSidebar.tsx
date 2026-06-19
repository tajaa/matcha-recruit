import { Building2, CalendarClock, Shield, Zap } from 'lucide-react'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'

// Standalone Matcha Compliance product sidebar. A matcha_compliance tenant has
// the full `compliance` feature on (flipped by the Stripe webhook), so the page
// renders ComplianceFull — no IR / employees / handbook surfaces here. Slim
// nav: the compliance dashboard, the compliance calendar, the company profile,
// and a re-entry into the setup wizard.
const nav: (NavItem | NavGroup)[] = [
  { to: '/app/compliance', icon: Shield, label: 'Compliance' },
  { to: '/app/compliance-calendar', icon: CalendarClock, label: 'Compliance Calendar' },
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
