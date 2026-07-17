import {
  IconAudit, IconBook, IconCompany, IconDraft, IconIncident, IconLedger,
  IconPeople, IconResources, IconSeal, IconSetup, IconShield, IconSpark,
  IconSteps, IconTraining, IconTrend,
} from '../nav-icons'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'
import { useSidebarBadges } from '../../hooks/useSidebarBadges'
import { useWhatsNewBadge } from '../../hooks/useWhatsNewBadge'

// Matcha-X (mid tier) sidebar. Lite (IR + employees + handbook generation)
// PLUS the mid-tier modules: handbook audit, training, progressive discipline,
// credentialing. Each module nav item is feature-gated so it only renders when
// the tier overlay (TIER_REQUIRED_FEATURES["matcha_x"]) has it on.
//
// Grouped by the job being done rather than left as one flat list: at fifteen
// identically-weighted rows the rail had to be read top to bottom every time.
// The groups are the tier's actual modules, so they also make the shape of what
// this tier includes legible. Feature-gated items still drop out individually,
// and SidebarShell hides a group once every child is filtered away.
const nav: (NavItem | NavGroup)[] = [
  {
    label: 'Safety',
    defaultOpen: true,
    items: [
      { to: '/app/ir', icon: IconIncident, label: 'Incidents' },
      { to: '/app/ir/risk-insights', icon: IconTrend, label: 'Risk Insights' },
      { to: '/app/ir/osha', icon: IconLedger, label: 'OSHA Logs' },
    ],
  },
  {
    label: 'Policy',
    defaultOpen: true,
    items: [
      { to: '/app/handbooks', icon: IconBook, label: 'Handbooks' },
      { to: '/app/resources/handbook-audit', icon: IconAudit, label: 'Handbook Audit', feature: 'handbook_audit' },
      { to: '/app/handbook-pilot', icon: IconDraft, label: 'Handbook Pilot', feature: 'handbook_pilot' },
      { to: '/app/matcha-x/compliance', icon: IconShield, label: 'Compliance', feature: 'compliance_lite', tag: 'Pro' },
    ],
  },
  {
    label: 'People',
    defaultOpen: true,
    items: [
      { to: '/app/employees', icon: IconPeople, label: 'Employees', feature: 'employees' },
      { to: '/app/training', icon: IconTraining, label: 'Training', feature: 'training' },
      { to: '/app/discipline', icon: IconSteps, label: 'Performance Action', feature: 'discipline' },
      { to: '/app/credential-templates', icon: IconSeal, label: 'Credentialing', feature: 'credential_templates' },
    ],
  },
  {
    label: 'Workspace',
    defaultOpen: true,
    items: [
      { to: '/app/company', icon: IconCompany, label: 'Company' },
      { to: '/matcha-x/onboarding', icon: IconSetup, label: 'Compliance Setup' },
      { to: '/app/resources', icon: IconResources, label: 'Resources' },
      { to: '/app/whats-new', icon: IconSpark, label: "What's New" },
    ],
  },
]

export default function MatchaXSidebar() {
  const { me, loading } = useMe()
  const { badges, markSeen } = useSidebarBadges()
  const whatsNew = useWhatsNewBadge()

  // Badges attach by route, and every entry now lives inside a group — so this
  // has to walk into groups. Returning the group untouched (as this did while
  // the nav was flat) would silently drop the Incidents / What's New counts.
  const withBadge = (item: NavItem): NavItem => {
    if (item.to === '/app/ir') {
      return { ...item, badge: badges.ir || undefined, onSeen: () => markSeen('ir') }
    }
    if (item.to === '/app/whats-new') {
      return { ...item, badge: whatsNew.count || undefined, onSeen: whatsNew.markSeen }
    }
    return item
  }

  const items: (NavItem | NavGroup)[] = nav.map((entry) =>
    'items' in entry ? { ...entry, items: entry.items.map(withBadge) } : withBadge(entry)
  )

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
