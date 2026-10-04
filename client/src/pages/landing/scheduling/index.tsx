import { lazy, Suspense, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useMarketingBoard } from '../../../components/marketing/kit/hooks'
import { useSEO } from '../../../hooks/useSEO'
import { Change } from './sections/Change'
import { Check } from './sections/Check'
import { Closing } from './sections/Closing'
import { Cost } from './sections/Cost'
import { Draft } from './sections/Draft'
import { Footer, Grain, LandingStyles, TimelineRail, TopBar } from './sections/Chrome'
import { Hero } from './sections/Hero'
import { Publish } from './sections/Publish'
import { IncidentsClosing } from './incidents/Closing'
import { IncidentsHero } from './incidents/Hero'
import { Approve, Report, Signed, Triage, WriteUp } from './incidents/Sections'
import { INCIDENT_STEPS, type LandingTab } from './styles'
import { BODY, INK, PAPER } from '../../../components/marketing/kit/theme'
import { BuyerGuide, BuyerQuestions, BuyerTopBar, OperationFit, Recovery, Setup } from './buyers/BuyerSections'
import { Pricing } from './buyers/Pricing'
import { Value } from './buyers/Value'

const PricingContactModal = lazy(() =>
  import('../../../components/marketing/PricingContactModal').then((m) => ({
    default: m?.PricingContactModal ?? (() => null),
  })),
)

// Two tabs, two routes: `/` is the home page and sells scheduling; `/incidents`
// is the same shell selling the incident-to-signed-copy workflow.
const SEO: Record<LandingTab, { title: string; description: string; canonical: string; jsonLd: object }> = {
  scheduling: {
    title: 'Matcha Scheduling — Next week’s schedule, already written',
    description:
      'Shift scheduling for cafés, restaurants, and shops. Matcha drafts the week from your sales, the weather, and who can work, then checks overtime, rest, and availability before you publish.',
    canonical: 'https://hey-matcha.com/',
    jsonLd: {
      '@context': 'https://schema.org',
      '@type': 'SoftwareApplication',
      name: 'Matcha Scheduling',
      applicationCategory: 'BusinessApplication',
      operatingSystem: 'Web',
      url: 'https://hey-matcha.com/',
      description:
        'Shift scheduling for cafés, restaurants, and shops. Drafts the week from sales, weather, and availability, and checks overtime, rest, and qualifications before you publish.',
    },
  },
  incidents: {
    title: 'Matcha Incidents — From incident report to signed copy',
    description:
      'Matcha checks every incident against your handbook, opens a case when a policy was broken, and carries the write-up through review, HR approval, and a signed copy. It does the paperwork; people make every call.',
    canonical: 'https://hey-matcha.com/incidents',
    jsonLd: {
      '@context': 'https://schema.org',
      '@type': 'SoftwareApplication',
      name: 'Matcha Incidents',
      applicationCategory: 'BusinessApplication',
      operatingSystem: 'Web',
      url: 'https://hey-matcha.com/incidents',
      description:
        'Incident reporting that checks each report against your handbook, opens a case when a policy was broken, and tracks the write-up through HR approval to a verified signed copy.',
    },
  },
}

export default function SchedulingLanding({ tab = 'scheduling' }: { tab?: LandingTab }) {
  const { hash } = useLocation()
  const [contactOpen, setContactOpen] = useState(false)
  const [contactMounted, setContactMounted] = useState(false)
  const openContact = () => {
    setContactMounted(true)
    setContactOpen(true)
  }

  useMarketingBoard()
  useSEO(SEO[tab])
  // The route is lazy: the anchor target does not exist at redirect time.
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [hash, tab])

  return (
    <div className="sched-root min-h-screen overflow-x-clip" style={{ backgroundColor: PAPER, color: INK, fontFamily: BODY }}>
      <LandingStyles />
      <Grain />
      {contactMounted && (
        <Suspense fallback={null}>
          <PricingContactModal isOpen={contactOpen} onClose={() => setContactOpen(false)} mode="consultation" />
        </Suspense>
      )}
      {tab === 'scheduling' ? <BuyerTopBar /> : <TopBar onContact={openContact} tab={tab} />}
      {tab === 'incidents' ? (
        <>
          <TimelineRail steps={INCIDENT_STEPS} day={['Tue–Wed', 'Oct 6']} label="Incident timeline" />
          <IncidentsHero onContact={openContact} />
          <main>
            <Report />
            <Triage />
            <WriteUp />
            <Approve />
            <Signed />
            <IncidentsClosing onContact={openContact} />
          </main>
        </>
      ) : (
        <>
          <TimelineRail darkStep="cost" />
          <Hero onContact={openContact} showCommercial />
          <main>
            <BuyerGuide />
            <Draft />
            <Check />
            <Change />
            <Recovery />
            <Cost />
            <Publish />
            <Setup onContact={openContact} />
            <OperationFit />
            <Value onContact={openContact} />
            <Pricing onContact={openContact} />
            <BuyerQuestions onContact={openContact} />
            <Closing onContact={openContact} />
          </main>
        </>
      )}
      <Footer tab={tab} />
    </div>
  )
}
