import { lazy, Suspense, useState } from 'react'
import { useMarketingBoard } from '../../../components/marketing/kit/hooks'
import { useSEO } from '../../../hooks/useSEO'
import { Footer, Grain, LandingStyles } from './sections/Chrome'
import type { LandingTab } from './styles'
import { BODY, BOARD, INK, PAPER } from '../../../components/marketing/kit/theme'

// Each destination loads only its own content. Preloads follow the route in vite.config.ts.
const BusinessHome = lazy(() => import('../BusinessHome'))
const loadScheduling = () => import('./SchedulingTab')
const loadIncidents = () => import('./IncidentsTab')
const SchedulingTab = lazy(loadScheduling)
const IncidentsTab = lazy(loadIncidents)

const PricingContactModal = lazy(() =>
  import('../../../components/marketing/PricingContactModal').then((m) => ({
    default: m?.PricingContactModal ?? (() => null),
  })),
)

// The business overview and both software products share the marketing shell.
const SEO: Record<LandingTab, { title: string; description: string; canonical: string; jsonLd: object }> = {
  home: {
    title: 'Matcha — HR, operations & technology for growing businesses',
    description: 'HR compliance, employee relations, and hiring. Better operational workflows. Websites, security, closed AI systems, and custom software. Matcha helps growing businesses run better.',
    canonical: 'https://hey-matcha.com/',
    jsonLd: {
      '@context': 'https://schema.org',
      '@type': 'Organization',
      name: 'Matcha',
      url: 'https://hey-matcha.com/',
      description: 'HR, operations, and technology support for growing businesses, alongside scheduling and incident reporting software.',
    },
  },
  scheduling: {
    title: 'Matcha Scheduling — Next week’s schedule, already written',
    description:
      'Shift scheduling for cafés, restaurants, and shops. Matcha drafts the week from your sales, the weather, and who can work, then checks overtime, rest, and availability before you publish.',
    canonical: 'https://hey-matcha.com/scheduling',
    jsonLd: {
      '@context': 'https://schema.org',
      '@type': 'SoftwareApplication',
      name: 'Matcha Scheduling',
      applicationCategory: 'BusinessApplication',
      operatingSystem: 'Web',
      url: 'https://hey-matcha.com/scheduling',
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

export default function SchedulingLanding({ tab = 'home' }: { tab?: LandingTab }) {
  const [contactOpen, setContactOpen] = useState(false)
  const [contactMounted, setContactMounted] = useState(false)
  const openContact = () => {
    setContactMounted(true)
    setContactOpen(true)
  }

  useMarketingBoard()
  useSEO(SEO[tab])

  return (
    <div className="sched-root min-h-screen overflow-x-clip" style={{ backgroundColor: PAPER, color: INK, fontFamily: BODY }}>
      <LandingStyles />
      <Grain />
      {contactMounted && (
        <Suspense fallback={null}>
          <PricingContactModal isOpen={contactOpen} onClose={() => setContactOpen(false)} mode="consultation" />
        </Suspense>
      )}
      {/* All destinations open on the dark hero; hold its colour while the chunk arrives. */}
      <Suspense fallback={<div aria-hidden className="min-h-screen" style={{ backgroundColor: BOARD.PAPER }} />}>
        {tab === 'home' ? <BusinessHome onContact={openContact} /> : tab === 'incidents' ? <IncidentsTab onContact={openContact} /> : <SchedulingTab onContact={openContact} />}
      </Suspense>
      <Footer tab={tab} />
    </div>
  )
}
