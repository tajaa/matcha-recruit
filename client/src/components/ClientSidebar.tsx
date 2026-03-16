import { LayoutDashboard, Users, Shield, FileText, ClipboardCheck, Scale, AlertTriangle, BookOpen } from 'lucide-react'
import SidebarShell from './SidebarShell'

const nav = [
  { to: '/app', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/app/employees', icon: Users, label: 'Employees' },
  { to: '/app/onboarding', icon: ClipboardCheck, label: 'Onboarding' },
  { to: '/app/er-copilot', icon: Scale, label: 'ER Copilot' },
  { to: '/app/ir', icon: AlertTriangle, label: 'Incidents' },
  { to: '/app/compliance', icon: Shield, label: 'Compliance' },
  { to: '/app/policies', icon: FileText, label: 'Policies' },
  { to: '/app/handbooks', icon: BookOpen, label: 'Handbooks' },
]

export default function ClientSidebar() {
  return <SidebarShell logoTo="/app" logoLabel="Matcha" nav={nav} />
}
