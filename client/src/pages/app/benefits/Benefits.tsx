import { useEffect, useState } from 'react'
import { HeartPulse } from 'lucide-react'
import { PillTabs } from '../../../components/ui'
import { EligibilityTab } from '../../../components/benefits/EligibilityTab'
import { ElectionsReviewTab } from '../../../components/benefits/ElectionsReviewTab'
import { EnrollmentPeriodsTab } from '../../../components/benefits/EnrollmentPeriodsTab'
import { LifeEventsTab } from '../../../components/benefits/LifeEventsTab'
import { PlansTab } from '../../../components/benefits/PlansTab'
import { benefitsApi } from '../../../api/benefits/benefits'
import type { OePeriod } from '../../../api/benefits/benefits'

type Tab = 'plans' | 'periods' | 'elections' | 'life-events' | 'eligibility'

const TABS: { value: Tab; label: string }[] = [
  { value: 'plans', label: 'Plans' },
  { value: 'periods', label: 'Enrollment periods' },
  { value: 'elections', label: 'Elections' },
  { value: 'life-events', label: 'Life events' },
  { value: 'eligibility', label: 'Eligibility & risk' },
]

export default function Benefits() {
  const [tab, setTab] = useState<Tab>('plans')
  const [periods, setPeriods] = useState<OePeriod[]>([])

  useEffect(() => {
    benefitsApi.listPeriods().then((res) => setPeriods(res.periods)).catch(() => setPeriods([]))
  }, [tab])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-zinc-100">
          <HeartPulse className="w-5 h-5" />
          Benefits
        </h1>
        <p className="text-sm text-zinc-500 mt-1">
          Plan catalog, open enrollment, elections, and eligibility risk.
        </p>
      </div>

      <PillTabs options={TABS} value={tab} onChange={setTab} />

      {tab === 'plans' && <PlansTab />}
      {tab === 'periods' && <EnrollmentPeriodsTab onSelect={() => setTab('elections')} />}
      {tab === 'elections' && <ElectionsReviewTab periods={periods} />}
      {tab === 'life-events' && <LifeEventsTab />}
      {tab === 'eligibility' && <EligibilityTab />}
    </div>
  )
}
