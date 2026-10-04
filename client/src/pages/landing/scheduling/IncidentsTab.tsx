import { TimelineRail, TopBar } from './sections/Chrome'
import { IncidentsClosing } from './incidents/Closing'
import { IncidentsHero } from './incidents/Hero'
import { Approve, Report, Signed, Triage, WriteUp } from './incidents/Sections'
import { INCIDENT_STEPS } from './styles'
import { useHashScroll } from './useHashScroll'

/** `/incidents` — the incident-to-signed-copy workflow. */
export default function IncidentsTab({ onContact }: { onContact: () => void }) {
  useHashScroll()
  return (
    <>
      <TopBar onContact={onContact} tab="incidents" />
      <TimelineRail steps={INCIDENT_STEPS} day={['Tue–Wed', 'Oct 6']} label="Incident timeline" />
      <IncidentsHero onContact={onContact} />
      <main>
        <Report />
        <Triage />
        <WriteUp />
        <Approve />
        <Signed />
        <IncidentsClosing onContact={onContact} />
      </main>
    </>
  )
}
