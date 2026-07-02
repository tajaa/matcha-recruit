import { BadgeCheck, Building2, CalendarClock, FileText, Shield, ShieldAlert, Sparkles, Users, Zap } from 'lucide-react'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'
import { useWhatsNewBadge } from '../../hooks/useWhatsNewBadge'

// Standalone Matcha Compliance product sidebar. A paid matcha_compliance tenant
// has `compliance` on (flipped by the Stripe webhook) plus the four-pillar
// bundle granted by the matcha_compliance TIER_REQUIRED overlay: handbook
// audit, policy management, and credentialing (with the employee roster it
// needs). Each pillar nav item is feature-gated so it only renders when the
// overlay flag is on — the pending shell handles the unpaid state upstream.
const nav: (NavItem | NavGroup)[] = [
  { to: '/app/compliance', icon: Shield, label: 'Compliance' },
  { to: '/app/compliance-calendar', icon: CalendarClock, label: 'Compliance Calendar' },
  { to: '/app/resources/handbook-audit', icon: ShieldAlert, label: 'Handbook Audit', feature: 'handbook_audit' },
  { to: '/app/policies', icon: FileText, label: 'Policy Management', feature: 'policies' },
  { to: '/app/credential-templates', icon: BadgeCheck, label: 'Credentialing', feature: 'credential_templates' },
  { to: '/app/employees', icon: Users, label: 'Employees', feature: 'employees' },
  { to: '/app/whats-new', icon: Sparkles, label: "What's New" },
  { to: '/app/company', icon: Building2, label: 'Company' },
  { to: '/compliance/onboarding', icon: Zap, label: 'Compliance Setup' },
]

export default function ComplianceSidebar() {
  const { me, loading } = useMe()
  const whatsNew = useWhatsNewBadge()
  const footerName = me?.profile?.company_name

  const items: (NavItem | NavGroup)[] = nav.map((item) => {
    if ('items' in item) return item
    if (item.to === '/app/whats-new') {
      return { ...item, badge: whatsNew.count || undefined, onSeen: whatsNew.markSeen }
    }
    return item
  })

  return (
    <SidebarShell
      logoTo="/app/compliance"
      logoLabel="Matcha Compliance"
      nav={loading ? [] : items}
      user={footerName ? {
        name: footerName,
        avatarUrl: me?.user?.avatar_url,
        settingsTo: '/app/settings',
      } : undefined}
    />
  )
}
