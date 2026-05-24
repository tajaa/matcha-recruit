import { useState } from 'react'
import { AlertTriangle, BookOpen, Calculator, ClipboardCheck, FileText, Home, Library, Newspaper, ShieldAlert } from 'lucide-react'
import SidebarShell from '../SidebarShell'
import type { NavItem, NavGroup } from '../SidebarShell'
import { useMe } from '../../hooks/useMe'
import UpgradePanel from './UpgradePanel'
import { UpgradeRequestModal } from './UpgradeRequestModal'

export default function ResourcesFreeSidebar() {
  const { me, loading } = useMe()
  const [requestOpen, setRequestOpen] = useState(false)
  const footerName = me?.profile?.company_name

  const nav: (NavItem | NavGroup)[] = [
    { to: '/app/resources', icon: Home, label: 'Hub' },
    {
      label: 'Resources',
      items: [
        { to: '/app/resources/templates', icon: FileText, label: 'Templates' },
        { to: '/app/resources/templates/job-descriptions', icon: Library, label: 'Job Descriptions' },
        { to: '/app/resources/calculators', icon: Calculator, label: 'Calculators' },
        { to: '/app/resources/audit', icon: ClipboardCheck, label: 'Compliance Audit' },
        { to: '/app/resources/handbook-audit', icon: ShieldAlert, label: 'Handbook Audit' },
        { to: '/app/resources/glossary', icon: BookOpen, label: 'HR Glossary' },
        { to: '/app/resources/headlines', icon: Newspaper, label: 'Weekly Headlines' },
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
          onLockedClick: () => setRequestOpen(true),
        },
      ],
    },
  ]

  return (
    <>
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
      <UpgradeRequestModal isOpen={requestOpen} onClose={() => setRequestOpen(false)} />
    </>
  )
}
