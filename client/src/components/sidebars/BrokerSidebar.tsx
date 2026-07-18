import { useState, useEffect } from 'react'
import { LayoutDashboard, Building2, Settings, Zap, Globe, Activity, Warehouse, Sparkles } from 'lucide-react'
import SidebarShell, { type NavItem } from './SidebarShell'
import ThemeToggle from '../shared/ThemeToggle'
import { fetchBrokerRiskAlerts } from '../../api/broker/broker'
import { useMe } from '../../hooks/useMe'

export default function BrokerSidebar() {
  const { me } = useMe()
  const isPro = me?.profile?.plan === 'pro'
  const [actionCount, setActionCount] = useState(0)

  useEffect(() => {
    fetchBrokerRiskAlerts().then((alerts) => setActionCount(alerts.active_unread))
  }, [])

  const nav: NavItem[] = [
    { to: '/broker', icon: LayoutDashboard, label: 'Book of Business' },
    { to: '/broker/action-center', icon: Zap, label: 'Action Center', badge: actionCount },
    { to: '/broker/risk-curve', icon: Activity, label: 'Risk Curve' },
    { to: '/broker/property', icon: Warehouse, label: 'Property Book' },
    // Broker Pro: off-platform clients (not Matcha tenants). Admin-toggled entitlement.
    ...(isPro ? [{ to: '/broker/external', icon: Globe, label: 'External Book' } as NavItem] : []),
    // Broker Pro: grounded per-client analysis chat (uploaded docs + platform data).
    ...(isPro ? [{ to: '/broker/pilot', icon: Sparkles, label: 'Broker Pilot' } as NavItem] : []),
    // Clients hub (onboarding · pipeline · seats · referrals) + Account hub (team · settings).
    { to: '/broker/clients', icon: Building2, label: 'Clients' },
    { to: '/broker/account', icon: Settings, label: 'Account' },
  ]

  return (
    <SidebarShell
      logoTo="/broker"
      logoLabel="Matcha Broker"
      nav={nav}
      footerSlot={<ThemeToggle />}
    />
  )
}
