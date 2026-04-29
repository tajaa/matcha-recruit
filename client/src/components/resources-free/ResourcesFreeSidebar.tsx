import { BookOpen, Calculator, ClipboardCheck, FileText, Library } from 'lucide-react'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'
import UpgradePanel from './UpgradePanel'

const nav: (NavItem | NavGroup)[] = [
  { to: '/resources/templates', icon: FileText, label: 'Templates' },
  { to: '/resources/templates/job-descriptions', icon: Library, label: 'Job Descriptions' },
  { to: '/resources/calculators', icon: Calculator, label: 'Calculators' },
  { to: '/resources/audit', icon: ClipboardCheck, label: 'Compliance Audit' },
  { to: '/resources/glossary', icon: BookOpen, label: 'HR Glossary' },
]

/**
 * Sidebar for free Resources-tier tenants. Slim nav (just the resources hub)
 * plus a prominent UpgradePanel that pitches Matcha IR (Stripe checkout) and
 * the full platform (contact sales).
 */
export default function ResourcesFreeSidebar() {
  const { me, loading } = useMe()
  const footerName = me?.profile?.company_name

  return (
    <SidebarShell
      logoTo="/resources"
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
