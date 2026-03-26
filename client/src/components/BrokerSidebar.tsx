import { LayoutDashboard, Building2, Settings } from 'lucide-react'
import SidebarShell from './SidebarShell'

const nav = [
  { to: '/broker', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/broker/clients', icon: Building2, label: 'Client Onboarding' },
  { to: '/broker/settings', icon: Settings, label: 'Settings' },
]

export default function BrokerSidebar() {
  return <SidebarShell logoTo="/broker" logoLabel="Matcha Broker" nav={nav} />
}
