import { useState } from 'react'
import { AlertTriangle, BookOpen, Calculator, ClipboardCheck, FileText, Home, Library } from 'lucide-react'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'
import { api } from '../../api/client'
import UpgradePanel from './UpgradePanel'

interface CheckoutResponse {
  checkout_url: string
  stripe_session_id: string
}

/**
 * Sidebar for free Resources-tier tenants. Lives inside the /app shell so
 * resources_free users get the same internal experience as paid tenants.
 *
 * Nav points to embedded /app/resources/* routes (the in-shell versions of
 * the public marketing pages). The IR tab is locked + grayed; clicking it
 * starts the Matcha IR Stripe-hosted checkout.
 */
export default function ResourcesFreeSidebar() {
  const { me, loading } = useMe()
  const [checkoutLoading, setCheckoutLoading] = useState(false)
  const footerName = me?.profile?.company_name

  async function startIrCheckout() {
    if (checkoutLoading) return
    setCheckoutLoading(true)
    try {
      const res = await api.post<CheckoutResponse>('/resources/upgrade/ir/checkout', {
        success_url: `${window.location.origin}/app/ir?upgraded=ir`,
        cancel_url: `${window.location.origin}/app?upgrade_canceled=1`,
      })
      window.location.href = res.checkout_url
    } catch {
      setCheckoutLoading(false)
    }
  }

  const nav: (NavItem | NavGroup)[] = [
    { to: '/app/resources', icon: Home, label: 'Hub' },
    {
      label: 'Resources',
      items: [
        { to: '/app/resources/templates', icon: FileText, label: 'Templates' },
        { to: '/app/resources/templates/job-descriptions', icon: Library, label: 'Job Descriptions' },
        { to: '/app/resources/calculators', icon: Calculator, label: 'Calculators' },
        { to: '/app/resources/audit', icon: ClipboardCheck, label: 'Compliance Audit' },
        { to: '/app/resources/glossary', icon: BookOpen, label: 'HR Glossary' },
      ],
    },
    {
      label: 'Upgrade',
      items: [
        {
          to: '/app/ir',
          icon: AlertTriangle,
          label: 'Incident Reporting',
          locked: true,
          onLockedClick: startIrCheckout,
        },
      ],
    },
  ]

  return (
    <SidebarShell
      logoTo="/app/resources"
      logoLabel="Matcha"
      nav={loading ? [] : nav}
      upgradeFooter={<UpgradePanel />}
      user={footerName ? {
        name: footerName,
        avatarUrl: me?.user?.avatar_url,
        settingsTo: '/app/settings',
      } : undefined}
    />
  )
}
