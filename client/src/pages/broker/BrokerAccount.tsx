import { useSearchParams } from 'react-router-dom'
import { UserPlus, Settings } from 'lucide-react'
import { PageHeader } from '../../components/broker/PageHeader'
import { TabBar, type TabDef } from '../../components/broker/TabBar'
import BrokerTeam from './BrokerTeam'
import BrokerSettings from './BrokerSettings'

const TABS: TabDef[] = [
  { key: 'team', label: 'Team', icon: UserPlus },
  { key: 'settings', label: 'Settings', icon: Settings },
]
const DEFAULT_TAB = 'team'

/**
 * Account hub — broker org settings under one tabbed page: teammates and
 * account/login preferences. Legacy /broker/team and /broker/settings redirect here.
 */
export default function BrokerAccount() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab') ?? DEFAULT_TAB
  const active = TABS.some((t) => t.key === raw) ? raw : DEFAULT_TAB

  function setTab(key: string) {
    setParams(key === DEFAULT_TAB ? {} : { tab: key }, { replace: true })
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Account" subtitle="Your broker team and account settings." />
      <TabBar tabs={TABS} active={active} onChange={setTab} />
      <div>
        {active === 'team' && <BrokerTeam embedded />}
        {active === 'settings' && <BrokerSettings embedded />}
      </div>
    </div>
  )
}
