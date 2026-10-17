import { AdminTabs } from '../../../../components/admin/AdminTabs'
/**
 * Gap-analysis landing — the master-admin home at /admin/gap-analysis.
 *
 * Lands on the companies DASHBOARD (overview/triage), not the wizard. Two tabs:
 *   • Dashboard  — every company's coverage / gaps / drift, searchable; click in
 *                  to a company's live gap dashboard.
 *   • Onboarding — take a new company through the wizard, or resume a session.
 */
import { AdminPageHeader } from '../../../../components/admin/AdminPageHeader'
import { useState } from 'react'
import { LayoutGrid, ClipboardList } from 'lucide-react'
import GapOverview from './GapOverview'
import AdminOnboarding from './AdminOnboarding'

type Tab = 'dashboard' | 'onboarding'

export default function GapAnalysisHome() {
  const [tab, setTab] = useState<Tab>('dashboard')

  return (
    <div>
      <AdminPageHeader title="Gap Analysis" description="Compliance scope across all companies — initial and continuous onboarding." />

      <AdminTabs label="Gap analysis views" value={tab} onChange={setTab} options={[{ value: 'dashboard', label: <><LayoutGrid size={14} />Dashboard</> }, { value: 'onboarding', label: <><ClipboardList size={14} />Onboarding</> }]} />

      {tab === 'dashboard' ? <GapOverview /> : <AdminOnboarding embedded />}
    </div>
  )
}
