import {
  LayoutDashboard, Users, Shield, FileText, ClipboardCheck, Scale,
  AlertTriangle, BookOpen, BarChart2, Sparkles, Building2, Accessibility,
  BadgeCheck, MessageSquareWarning, Mail, Bell,
} from 'lucide-react'
import SidebarShell from './SidebarShell'
import type { NavGroup, NavItem } from './SidebarShell'
import { useMe } from '../hooks/useMe'

const nav: (NavItem | NavGroup)[] = [
  { to: '/app', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/app/company', icon: Building2, label: 'Company' },
  {
    label: 'HR Ops',
    items: [
      { to: '/app/employees', icon: Users, label: 'Employees' },
      { to: '/app/onboarding', icon: ClipboardCheck, label: 'Onboarding' },
      { to: '/app/accommodations', icon: Accessibility, label: 'Accommodations' },
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
  const { me, loading, isPersonal } = useMe()

  return (
    <SidebarShell
      logoTo={isPersonal ? '/work' : '/app'}
      logoLabel="Matcha"
      nav={loading ? [] : isPersonal ? personalNav : nav}
      user={me?.profile ? {
        name: me.profile.name,
        avatarUrl: me.user?.avatar_url,
        settingsTo: '/app/settings',
      } : undefined}
    />
  )
}
