import { LayoutDashboard, Building2, Link2, Settings, Shield, AlertTriangle } from 'lucide-react'
import SidebarShell from './SidebarShell'

const nav = [
  { to: '/broker', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/broker/clients', icon: Building2, label: 'Client Onboarding' },
  { to: '/broker/wc-portfolio', icon: Shield, label: 'WC Portfolio' },
  { to: '/broker/risk-alerts', icon: AlertTriangle, label: 'Risk Alerts' },
  { to: '/broker/referrals', icon: Link2, label: 'Referral Links' },
  { to: '/broker/settings', icon: Settings, label: 'Settings' },
]

export default function BrokerSidebar() {
  return <SidebarShell logoTo="/broker" logoLabel="Matcha Broker" nav={nav} />
}
