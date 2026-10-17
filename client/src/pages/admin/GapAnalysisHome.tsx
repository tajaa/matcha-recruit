/**
 * Gap-analysis landing — the master-admin home at /admin/gap-analysis.
 *
 * Lands on the companies DASHBOARD (overview/triage), not the wizard. Two tabs:
 *   • Dashboard  — every company's coverage / gaps / drift, searchable; click in
 *                  to a company's live gap dashboard.
 *   • Onboarding — take a new company through the wizard, or resume a session.
 */
import { AdminPageHeader } from '../../components/admin/AdminPageHeader'
import { useState } from 'react'
import { LayoutGrid, ClipboardList } from 'lucide-react'
import GapOverview from './GapOverview'
import AdminOnboarding from './AdminOnboarding'

type Tab = 'dashboard' | 'onboarding'

export default function GapAnalysisHome() {
  const [tab, setTab] = useState<Tab>('dashboard')

  const tabClass = (t: Tab) =>
    `flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors ${
      tab === t ? 'border-b-2 border-vsc-accent text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
    }`

  return (
    <div>
      <AdminPageHeader title="Gap Analysis" description="Compliance scope across all companies — initial and continuous onboarding." />

      <div className="flex gap-1 border-b border-vsc-border mb-5">
        <button onClick={() => setTab('dashboard')} className={tabClass('dashboard')}>
          <LayoutGrid size={14} /> Dashboard
        </button>
        <button onClick={() => setTab('onboarding')} className={tabClass('onboarding')}>
          <ClipboardList size={14} /> Onboarding
        </button>
      </div>

      {tab === 'dashboard' ? <GapOverview /> : <AdminOnboarding embedded />}
    </div>
  )
}
