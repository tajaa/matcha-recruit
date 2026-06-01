import { LayoutDashboard, Building2, Link2, Settings, Shield, AlertTriangle, UserCheck, Radar } from 'lucide-react'
import SidebarShell from './SidebarShell'

const nav = [
  { to: '/broker', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/broker/clients', icon: Building2, label: 'Client Onboarding' },
  { to: '/broker/wc-portfolio', icon: Shield, label: 'WC Portfolio' },
  { to: '/broker/risk-alerts', icon: AlertTriangle, label: 'Risk Alerts' },
  { to: '/broker/benefits/eligibility-exceptions', icon: UserCheck, label: 'Eligibility Exceptions' },
  { to: '/broker/benefits/renewal-risk-radar', icon: Radar, label: 'Renewal Risk Radar' },
  { to: '/broker/referrals', icon: Link2, label: 'Referral Links' },
  { to: '/broker/settings', icon: Settings, label: 'Settings' },
]

export default function BrokerSidebar() {
  return <SidebarShell logoTo="/broker" logoLabel="Matcha Broker" nav={nav} />
}
