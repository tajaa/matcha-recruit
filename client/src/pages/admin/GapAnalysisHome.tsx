/**
 * Gap-analysis landing — the master-admin home at /admin/gap-analysis.
 *
 * Lands on the companies DASHBOARD (overview/triage), not the wizard. Two tabs:
 *   • Dashboard  — every company's coverage / gaps / drift, searchable; click in
 *                  to a company's live gap dashboard.
 *   • Onboarding — take a new company through the wizard, or resume a session.
 */
import { useState } from 'react'
import { Sparkles, LayoutGrid, ClipboardList } from 'lucide-react'
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
    <div className="p-6">
      <div className="flex items-center gap-3 mb-1">
        <Sparkles className="w-5 h-5 text-vsc-accent" />
        <h1 className="text-lg font-semibold text-zinc-100">Gap Analysis</h1>
      </div>
      <p className="text-xs text-zinc-500 mb-4">
        Compliance scope across all companies — initial and continuous onboarding.
      </p>

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
