import { useState, useEffect } from 'react'
import { LayoutDashboard, Building2, Settings, Zap, Globe } from 'lucide-react'
import SidebarShell, { type NavItem } from './SidebarShell'
import BrokerThemeToggle from './BrokerThemeToggle'
import { fetchBrokerRiskAlerts, fetchActionCenterMilestones } from '../api/broker'
import { useMe } from '../hooks/useMe'

export default function BrokerSidebar() {
  const { me } = useMe()
  const isPro = me?.profile?.plan === 'pro'
  const [actionCount, setActionCount] = useState(0)

  useEffect(() => {
    Promise.allSettled([
      fetchBrokerRiskAlerts(),
      fetchActionCenterMilestones(),
    ]).then(([alerts, milestones]) => {
      const unreadAlerts = alerts.status === 'fulfilled' ? alerts.value.active_unread : 0
      const unreadMilestones = milestones.status === 'fulfilled' ? milestones.value.summary.unread : 0
      setActionCount(unreadAlerts + unreadMilestones)
    })
  }, [])

  const nav: NavItem[] = [
    { to: '/broker', icon: LayoutDashboard, label: 'Book of Business' },
    { to: '/broker/action-center', icon: Zap, label: 'Action Center', badge: actionCount },
    // Broker Pro: off-platform clients (not Matcha tenants). Admin-toggled entitlement.
    ...(isPro ? [{ to: '/broker/external', icon: Globe, label: 'External Book' } as NavItem] : []),
    // Clients hub (onboarding · pipeline · seats · referrals) + Account hub (team · settings).
    { to: '/broker/clients', icon: Building2, label: 'Clients' },
    { to: '/broker/account', icon: Settings, label: 'Account' },
  ]

  return (
    <SidebarShell
      logoTo="/broker"
      logoLabel="Matcha Broker"
      nav={nav}
      footerSlot={<BrokerThemeToggle />}
    />
  )
}
