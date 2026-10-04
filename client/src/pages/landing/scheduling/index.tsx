import { lazy, Suspense, useEffect, useState } from 'react'
import { useIdle, useMarketingBoard } from '../../../components/marketing/kit/hooks'
import { useSEO } from '../../../hooks/useSEO'
import { Footer, Grain, LandingStyles } from './sections/Chrome'
import type { LandingTab } from './styles'
import { BODY, BOARD, INK, PAPER } from '../../../components/marketing/kit/theme'

// Each tab is its own chunk, so `/` never downloads the incident sections (and
// the reverse). index.html preloads the one the URL needs; see vite.config.ts.
const loadScheduling = () => import('./SchedulingTab')
const loadIncidents = () => import('./IncidentsTab')
const SchedulingTab = lazy(loadScheduling)
const IncidentsTab = lazy(loadIncidents)

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
  const [contactOpen, setContactOpen] = useState(false)
  const [contactMounted, setContactMounted] = useState(false)
  const openContact = () => {
    setContactMounted(true)
    setContactOpen(true)
  }

  useMarketingBoard()
  useSEO(SEO[tab])
  // Fetch the other tab once the page is idle, so switching does not wait on it.
  const idle = useIdle(true)
  useEffect(() => {
    if (idle) void (tab === 'incidents' ? loadScheduling : loadIncidents)().catch(() => {})
  }, [idle, tab])

  return (
    <div className="sched-root min-h-screen overflow-x-clip" style={{ backgroundColor: PAPER, color: INK, fontFamily: BODY }}>
      <LandingStyles />
      <Grain />
      {contactMounted && (
        <Suspense fallback={null}>
          <PricingContactModal isOpen={contactOpen} onClose={() => setContactOpen(false)} mode="consultation" />
        </Suspense>
      )}
      {/* Both tabs open on the dark hero; hold its colour while the chunk arrives. */}
      <Suspense fallback={<div aria-hidden className="min-h-screen" style={{ backgroundColor: BOARD.PAPER }} />}>
        {tab === 'incidents' ? <IncidentsTab onContact={openContact} /> : <SchedulingTab onContact={openContact} />}
      </Suspense>
      <Footer tab={tab} />
    </div>
  )
}
