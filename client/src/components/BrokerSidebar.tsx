import { LayoutDashboard } from 'lucide-react'
import SidebarShell from './SidebarShell'

const nav = [
  { to: '/broker', icon: LayoutDashboard, label: 'Dashboard' },
]

export default function BrokerSidebar() {
  return <SidebarShell logoTo="/broker" logoLabel="Matcha Broker" nav={nav} />
}
