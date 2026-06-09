import { useState, useEffect } from 'react'
import { LayoutDashboard, Building2, Link2, Settings, Zap, Workflow, Ticket, UserPlus } from 'lucide-react'
import SidebarShell, { type NavItem, type NavGroup } from './SidebarShell'
import BrokerThemeToggle from './BrokerThemeToggle'
import { fetchBrokerRiskAlerts, fetchActionCenterMilestones } from '../api/broker'

export default function BrokerSidebar() {
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

  const nav: (NavItem | NavGroup)[] = [
    { to: '/broker', icon: LayoutDashboard, label: 'Book of Business' },
    { to: '/broker/action-center', icon: Zap, label: 'Action Center', badge: actionCount },
    {
      label: 'Administration',
      items: [
        { to: '/broker/clients', icon: Building2, label: 'Onboarding' },
        { to: '/broker/seats', icon: Ticket, label: 'Client Seats' },
        { to: '/broker/pipeline', icon: Workflow, label: 'Pipeline' },
        { to: '/broker/referrals', icon: Link2, label: 'Referral Links' },
        { to: '/broker/team', icon: UserPlus, label: 'Team' },
        { to: '/broker/settings', icon: Settings, label: 'Settings' },
      ],
    },
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
