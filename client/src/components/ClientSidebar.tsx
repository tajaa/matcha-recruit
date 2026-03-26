import { LayoutDashboard, Users, Shield, FileText, ClipboardCheck, Scale, AlertTriangle, BookOpen, BarChart2, Sparkles, Building2, Accessibility, BadgeCheck } from 'lucide-react'
import SidebarShell from './SidebarShell'

const nav = [
  { to: '/app', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/app/company', icon: Building2, label: 'Company' },
  { to: '/app/employees', icon: Users, label: 'Employees' },
  { to: '/app/onboarding', icon: ClipboardCheck, label: 'Onboarding' },
  { to: '/app/er-copilot', icon: Scale, label: 'ER Copilot' },
  { to: '/app/ir', icon: AlertTriangle, label: 'Incidents' },
  { to: '/app/accommodations', icon: Accessibility, label: 'Accommodations' },
  { to: '/app/risk-assessment', icon: BarChart2, label: 'Risk Assessment' },
  { to: '/app/credential-templates', icon: BadgeCheck, label: 'Credentialing' },
  { to: '/app/compliance', icon: Shield, label: 'Compliance' },
  { to: '/app/policies', icon: FileText, label: 'Policies' },
  { to: '/app/handbooks', icon: BookOpen, label: 'Handbooks' },
  { to: '/work', icon: Sparkles, label: 'Matcha Work' },
]

export default function ClientSidebar() {
  return <SidebarShell logoTo="/app" logoLabel="Matcha" nav={nav} />
}
