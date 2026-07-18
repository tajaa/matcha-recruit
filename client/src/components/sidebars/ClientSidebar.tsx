import {
  LayoutDashboard, Users, Shield, FileText, ClipboardCheck, Scale,
  AlertTriangle, BookOpen, BarChart2, Sparkles, Building2, Accessibility,
  BadgeCheck, MessageSquareWarning, Mail, Bell, Gavel, MapPin, CalendarDays,
  GraduationCap, TrendingUp, ClipboardList, ShieldAlert, MessagesSquare, Handshake, ShieldCheck, Gauge, HeartPulse, FileCheck, Car, Link2, Activity,
  Coins, FileSignature, CalendarClock,
} from 'lucide-react'
import SidebarShell from './SidebarShell'
import type { NavGroup, NavItem } from './SidebarShell'
import { useMe } from '../../hooks/useMe'
import { useSidebarBadges } from '../../hooks/useSidebarBadges'

const nav: (NavItem | NavGroup)[] = [
  { to: '/app', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/app/company', icon: Building2, label: 'Company' },
  {
    label: 'HR Ops',
    items: [
      { to: '/app/employees', icon: Users, label: 'Employees' },
      { to: '/app/employee-schedule', icon: CalendarClock, label: 'Schedule', feature: 'employee_schedule' },
      { to: '/app/onboarding', icon: ClipboardCheck, label: 'Onboarding' },
      { to: '/app/accommodations', icon: Accessibility, label: 'Accommodations' },
      { to: '/app/discipline', icon: Gavel, label: 'Performance Action', feature: 'discipline' },
      { to: '/app/labor', icon: Handshake, label: 'Labor Relations', feature: 'labor_relations' },
    ],
  },
  {
    label: 'Compliance',
    items: [
      { to: '/app/compliance', icon: Shield, label: 'Compliance' },
      // No single `feature` here — gated below via COMPLIANCE_CALENDAR_FEATURES
      // (NavItem only supports one flag; the backend accepts any of three).
      { to: '/app/compliance-calendar', icon: CalendarDays, label: 'Calendar' },
      { to: '/app/policies', icon: FileText, label: 'Policies' },
      { to: '/app/handbooks', icon: BookOpen, label: 'Handbooks' },
      // Handbook Audit dropped from this tier's nav: Pro stores handbook_pilot
      // alongside handbook_audit at signup, and Pilot supersedes the gap-
      // analyzer-in-app-shell audit for the tiers that have both. The route
      // and flag stay live — Compliance and Free still use it, and neither
      // has handbook_pilot to fall back to.
      { to: '/app/handbook-pilot', icon: Sparkles, label: 'Handbook Pilot', feature: 'handbook_pilot' },
      { to: '/app/training', icon: GraduationCap, label: 'Training', feature: 'training' },
      { to: '/app/credential-templates', icon: BadgeCheck, label: 'Credentialing', feature: 'credential_templates' },
      { to: '/app/workforce-compliance', icon: ShieldCheck, label: 'Workforce Compliance', feature: 'workforce_compliance' },
      { to: '/app/risk-profile', icon: Gauge, label: 'Risk Profile', feature: 'risk_profile' },
      { to: '/app/controls-evidence', icon: FileCheck, label: 'Proof of Controls', feature: 'controls_evidence' },
      { to: '/app/limit-adequacy', icon: Scale, label: 'Limit Adequacy', feature: 'limit_adequacy' },
      { to: '/app/driver-risk', icon: Car, label: 'Driver Risk', feature: 'driver_risk' },
      { to: '/app/property', icon: Building2, label: 'Commercial Property', feature: 'property' },
      { to: '/app/tcor', icon: Coins, label: 'Total Cost of Risk', feature: 'tcor' },
      { to: '/app/coi', icon: FileText, label: 'Certificate Tracking', feature: 'coi_tracking' },
      { to: '/app/ir/insurance', icon: ShieldCheck, label: 'Insurance', feature: 'carrier_quotes' },
      { to: '/app/management-liability', icon: ShieldAlert, label: 'D&O Readiness', feature: 'do_readiness' },
      { to: '/app/acord', icon: FileSignature, label: 'ACORD Forms', feature: 'acord_forms' },
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
      { to: '/app/ir', icon: AlertTriangle, label: 'Incidents', feature: 'incidents' },
      { to: '/app/ir/risk-insights', icon: TrendingUp, label: 'Risk Insights', feature: 'incidents' },
      { to: '/app/ir/osha', icon: ClipboardList, label: 'OSHA Logs', feature: 'incidents' },
      { to: '/app/ir/magic-links', icon: Link2, label: 'Magic Links', feature: 'incidents' },
      { to: '/app/locations', icon: MapPin, label: 'Locations', feature: 'incidents' },
      { to: '/app/er-copilot', icon: Scale, label: 'ER Copilot' },
      { to: '/app/risk-assessment', icon: BarChart2, label: 'Risk Assessment' },
      { to: '/app/resident-care', icon: HeartPulse, label: 'Resident-Care Risk', feature: 'resident_care' },
      { to: '/app/legal-pilot', icon: Gavel, label: 'Legal Pilot', feature: 'legal_defense' },
    ],
  },
  {
    label: 'AI',
    items: [
      { to: '/work', icon: Sparkles, label: 'Matcha-Work' },
      { to: '/werk-lite', icon: MessagesSquare, label: 'Werk Lite', feature: 'werk_lite' },
      { to: '/app/analysis-pilot', icon: Activity, label: 'Analysis Pilot', feature: 'analysis_pilot' },
    ],
  },
]

// GET /compliance/calendar accepts any of these three flags (matches the
// backend `lite_router` gate) — kept here since NavItem only supports one.
const COMPLIANCE_CALENDAR_FEATURES = ['compliance', 'compliance_lite', 'incidents']

// Personal accounts only see Werk — no platform/HR items
const personalNav: (NavItem | NavGroup)[] = [
  {
    label: 'AI',
    items: [
      { to: '/werk', icon: Sparkles, label: 'Werk' },
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
        const filteredItems = item.items.filter((child) => {
          if (child.to === '/app/compliance-calendar') {
            return COMPLIANCE_CALENDAR_FEATURES.some((f) => hasFeature(f))
          }
          return !child.feature || hasFeature(child.feature)
        })
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
      logoTo={isPersonal ? '/werk' : '/app'}
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
