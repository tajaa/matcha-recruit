import { lazy, Suspense, useState } from 'react'
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
import { BODY, INK, PAPER } from '../../../components/marketing/kit/theme'

const PricingContactModal = lazy(() =>
  import('../../../components/marketing/PricingContactModal').then((m) => ({
    default: m?.PricingContactModal ?? (() => null),
  })),
)

const CANONICAL = 'https://hey-matcha.com/matcha-scheduling'

const JSON_LD = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'Matcha Scheduling',
  applicationCategory: 'BusinessApplication',
  operatingSystem: 'Web',
  url: CANONICAL,
  description:
    'Shift scheduling for cafés, restaurants, and shops. Drafts the week from sales, weather, and availability, and checks overtime, rest, and qualifications before you publish.',
}

export default function SchedulingLanding() {
  const [contactOpen, setContactOpen] = useState(false)
  const [contactMounted, setContactMounted] = useState(false)
  const openContact = () => {
    setContactMounted(true)
    setContactOpen(true)
  }

  useMarketingBoard()
  useSEO({
    title: 'Matcha Scheduling — Next week’s schedule, already written',
    description:
      'Shift scheduling for cafés, restaurants, and shops. Matcha drafts the week from your sales, the weather, and who can work, then checks overtime, rest, and availability before you publish.',
    canonical: CANONICAL,
    jsonLd: JSON_LD,
  })

  return (
    <div className="sched-root min-h-screen overflow-x-clip" style={{ backgroundColor: PAPER, color: INK, fontFamily: BODY }}>
      <LandingStyles />
      <Grain />
      {contactMounted && (
        <Suspense fallback={null}>
          <PricingContactModal isOpen={contactOpen} onClose={() => setContactOpen(false)} mode="consultation" />
        </Suspense>
      )}
      <TopBar onContact={openContact} />
      <TimelineRail />
      <Hero onContact={openContact} />
      <main>
        <Draft />
        <Check />
        <Change />
        <Cost />
        <Publish />
        <Closing onContact={openContact} />
      </main>
      <Footer />
    </div>
  )
}
