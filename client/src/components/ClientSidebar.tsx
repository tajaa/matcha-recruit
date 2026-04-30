import {
  LayoutDashboard, Users, Shield, FileText, ClipboardCheck, Scale,
  AlertTriangle, BookOpen, BarChart2, Sparkles, Building2, Accessibility,
  BadgeCheck, MessageSquareWarning, Mail, Bell, Gavel, MapPin,
} from 'lucide-react'
import SidebarShell from './SidebarShell'
import type { NavGroup, NavItem } from './SidebarShell'
import { useMe } from '../hooks/useMe'
import { useSidebarBadges } from '../hooks/useSidebarBadges'

const nav: (NavItem | NavGroup)[] = [
  { to: '/app', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/app/company', icon: Building2, label: 'Company' },
  {
    label: 'HR Ops',
    items: [
      { to: '/app/employees', icon: Users, label: 'Employees' },
      { to: '/app/onboarding', icon: ClipboardCheck, label: 'Onboarding' },
      { to: '/app/accommodations', icon: Accessibility, label: 'Accommodations' },
      { to: '/app/discipline', icon: Gavel, label: 'Performance Action', feature: 'discipline' },
    ],
  },
  {
    label: 'Compliance',
    items: [
      { to: '/app/compliance', icon: Shield, label: 'Compliance' },
      { to: '/app/policies', icon: FileText, label: 'Policies' },
      { to: '/app/handbooks', icon: BookOpen, label: 'Handbooks' },
      { to: '/app/credential-templates', icon: BadgeCheck, label: 'Credentialing' },
    ],
  },
  {
    label: 'Communication',
    items: [
      { to: '/app/inbox', icon: Mail, label: 'Inbox' },
      { to: '/app/notifications', icon: Bell, label: 'Notifications' },
      { to: '/app/escalated-queries', icon: MessageSquareWarning, label: 'Escalations' },
    ],
  },
  {
    label: 'Safety',
    items: [
      { to: '/app/ir', icon: AlertTriangle, label: 'Incidents' },
      { to: '/app/locations', icon: MapPin, label: 'Locations', feature: 'incidents' },
      { to: '/app/er-copilot', icon: Scale, label: 'ER Copilot' },
      { to: '/app/risk-assessment', icon: BarChart2, label: 'Risk Assessment' },
    ],
  },
  {
    label: 'AI',
    items: [
      { to: '/work', icon: Sparkles, label: 'Matcha Work' },
    ],
  },
]

// Personal accounts only see Matcha Work — no platform/HR items
const personalNav: (NavItem | NavGroup)[] = [
  {
    label: 'AI',
    items: [
      { to: '/work', icon: Sparkles, label: 'Matcha Work' },
    ],
  },
]

export default function ClientSidebar() {
  const { me, loading, isPersonal, hasFeature } = useMe()
  const { badges, markSeen } = useSidebarBadges()

  function filterByFeatures(items: (NavItem | NavGroup)[]): (NavItem | NavGroup)[] {
    const out: (NavItem | NavGroup)[] = []
    for (const item of items) {
      if ('items' in item) {
        if (item.feature && !hasFeature(item.feature)) continue
        const filteredItems = item.items.filter((child) => !child.feature || hasFeature(child.feature))
        if (filteredItems.length === 0) continue
        out.push({ ...item, items: filteredItems })
      } else {
        if (item.feature && !hasFeature(item.feature)) continue
        out.push(item)
      }
    }
    return out
  }

  function withBadges(items: (NavItem | NavGroup)[]): (NavItem | NavGroup)[] {
    return items.map((item) => {
      if ('items' in item) {
        return { ...item, items: item.items.map((child) => withBadges([child])[0] as NavItem) }
      }
      if (item.to === '/app/ir') return { ...item, badge: badges.ir || undefined, onSeen: () => markSeen('ir') }
      if (item.to === '/app/er-copilot') return { ...item, badge: badges.er || undefined, onSeen: () => markSeen('er') }
      if (item.to === '/app/escalated-queries') return { ...item, badge: badges.escalations || undefined, onSeen: () => markSeen('escalations') }
      if (item.to === '/app/inbox') return { ...item, badge: badges.inbox || undefined, onSeen: () => markSeen('inbox') }
      if (item.to === '/app/notifications') return { ...item, badge: badges.notifications || undefined, onSeen: () => markSeen('notifications') }
      return item
    })
  }

  // Footer shows the company context for business accounts (matches the
  // source used by the Company tab via /companies/me), and the user's own
  // name for personal accounts (which don't have a meaningful company).
  const footerName = me?.profile
    ? (isPersonal ? me.profile.name : me.profile.company_name)
    : undefined

  return (
    <SidebarShell
      logoTo={isPersonal ? '/work' : '/app'}
      logoLabel="Matcha"
      nav={loading ? [] : isPersonal ? personalNav : withBadges(filterByFeatures(nav))}
      user={footerName ? {
        name: footerName,
        avatarUrl: me?.user?.avatar_url,
        settingsTo: '/app/settings',
      } : undefined}
    />
  )
}
