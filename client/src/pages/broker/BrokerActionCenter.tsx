import BrokerRiskAlerts from './BrokerRiskAlerts'
import IntakeStatusPanel from '../../components/broker/action-center/IntakeStatusPanel'
import { HelpHint } from '../../components/broker/HelpHint'

// Renewals + Eligibility tabs paused 2026-06-08 — geared to EB brokers, low value.
// Page components (BrokerRenewalRiskRadar / BrokerEligibilityExceptions) kept; just
// unmounted from the tab bar. Legacy ?tab=renewals/eligibility URLs fall back to Alerts.
// Milestones tab removed 2026-07-02 — brokers prioritize negative action items over
// positive milestone tracking; MilestonesTab.tsx deleted, not just unmounted.

export default function BrokerActionCenter() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          Action Center
          <HelpHint text="Your daily worklist across the book. Alerts flag clients trending worse (rising injury rates, premium pressure). Work the list to stay ahead of renewals." />
        </h1>
        <p className="text-sm text-zinc-500 mt-1">
          Proactive signals across your book — from real-time risk alerts to consultative outreach.
        </p>
      </div>

      <BrokerRiskAlerts />
      <IntakeStatusPanel />
    </div>
  )
}
