import { useSearchParams } from 'react-router-dom'
import { Building2, Workflow, Ticket, Link2 } from 'lucide-react'
import { PageHeader } from '../../components/broker/PageHeader'
import { TabBar, type TabDef } from '../../components/broker/TabBar'
import BrokerClients from './BrokerClients'
import BrokerPipeline from './BrokerPipeline'
import BrokerClientSeats from './BrokerClientSeats'
import BrokerReferralLinks from './BrokerReferralLinks'

const TABS: TabDef[] = [
  { key: 'onboarding', label: 'Onboarding', icon: Building2 },
  { key: 'pipeline', label: 'Pipeline', icon: Workflow },
  { key: 'seats', label: 'Seats', icon: Ticket },
  { key: 'referrals', label: 'Referrals', icon: Link2 },
]
const DEFAULT_TAB = 'onboarding'

/**
 * Clients hub — folds the four client-acquisition surfaces (onboarding, pipeline,
 * seats, referrals) under one tabbed page. Tab persists in `?tab=`; legacy
 * standalone routes (/broker/seats etc.) redirect here.
 */
export default function BrokerClientsHub() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab') ?? DEFAULT_TAB
  const active = TABS.some((t) => t.key === raw) ? raw : DEFAULT_TAB

  function setTab(key: string) {
    setParams(key === DEFAULT_TAB ? {} : { tab: key }, { replace: true })
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Clients"
        subtitle="Onboard, track, and grow your referred book."
        hint="Everything to bring companies onto Matcha and keep deals moving — create setups, watch them through the pipeline, apportion seats, and share self-serve referral links."
      />
      <TabBar tabs={TABS} active={active} onChange={setTab} />
      <div>
        {active === 'onboarding' && <BrokerClients embedded />}
        {active === 'pipeline' && <BrokerPipeline embedded />}
        {active === 'seats' && <BrokerClientSeats embedded />}
        {active === 'referrals' && <BrokerReferralLinks embedded />}
      </div>
    </div>
  )
}
