import { useSearchParams } from 'react-router-dom'
import { AlertTriangle, Radar, UserCheck, Award } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import BrokerRiskAlerts from './BrokerRiskAlerts'
import BrokerRenewalRiskRadar from './BrokerRenewalRiskRadar'
import BrokerEligibilityExceptions from './BrokerEligibilityExceptions'
import MilestonesTab from '../../components/broker/action-center/MilestonesTab'

type TabKey = 'alerts' | 'renewals' | 'eligibility' | 'milestones'

const TABS: Array<{ key: TabKey; label: string; icon: LucideIcon }> = [
  { key: 'alerts', label: 'Alerts', icon: AlertTriangle },
  { key: 'renewals', label: 'Renewals', icon: Radar },
  { key: 'eligibility', label: 'Eligibility', icon: UserCheck },
  { key: 'milestones', label: 'Milestones', icon: Award },
]

export default function BrokerActionCenter() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab') as TabKey | null
  const active: TabKey = TABS.some((t) => t.key === raw) ? (raw as TabKey) : 'alerts'

  function setTab(key: TabKey) {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('tab', key)
      return next
    }, { replace: true })
  }

  return (
    <div className="space-y-6">
      {/* Header + tabs */}
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight">Action Center</h1>
        <p className="text-sm text-zinc-500 mt-1">
          Proactive signals across your book — from real-time risk alerts to consultative outreach.
        </p>
      </div>

      <div className="flex items-center gap-1 border-b border-white/5">
        {TABS.map((t) => {
          const isActive = t.key === active
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`relative flex items-center gap-1.5 px-3 py-2 text-[13px] transition-colors ${
                isActive ? 'text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              <t.icon className="w-3.5 h-3.5" />
              {t.label}
              {isActive && <span className="absolute left-0 right-0 -bottom-px h-0.5 bg-emerald-400 rounded-t" />}
            </button>
          )
        })}
      </div>

      {/* Panel — existing pages render unchanged inside their tabs. */}
      <div>
        {active === 'alerts' && <BrokerRiskAlerts />}
        {active === 'renewals' && <BrokerRenewalRiskRadar />}
        {active === 'eligibility' && <BrokerEligibilityExceptions />}
        {active === 'milestones' && <MilestonesTab />}
      </div>
    </div>
  )
}
