import { lazy, Suspense, useEffect, useState } from 'react'
import { useSEO } from '../../../hooks/useSEO'
import { Change } from './sections/Change'
import { Check } from './sections/Check'
import { Closing } from './sections/Closing'
import { Cost } from './sections/Cost'
import { Draft } from './sections/Draft'
import { Footer, Grain, LandingStyles, TimelineRail, TopBar } from './sections/Chrome'
import { Hero } from './sections/Hero'
import { Publish } from './sections/Publish'
import { BODY, FONT_HREF, INK, PAPER } from './theme'

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

/** Page-only fonts: injected here so index.html and every other page stay
 *  untouched. Preconnects first so the font files start with the CSS. */
function useFonts() {
  useEffect(() => {
    const head = document.head
    for (const href of ['https://fonts.googleapis.com', 'https://fonts.gstatic.com']) {
      if (head.querySelector(`link[rel="preconnect"][href="${href}"]`)) continue
      const pre = document.createElement('link')
      pre.rel = 'preconnect'
      pre.href = href
      if (href.includes('gstatic')) pre.crossOrigin = ''
      head.appendChild(pre)
    }
    if (head.querySelector(`link[href="${FONT_HREF}"]`)) return
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = FONT_HREF
    head.appendChild(link)
  }, [])
}

export default function SchedulingLanding() {
  const [contactOpen, setContactOpen] = useState(false)
  const [contactMounted, setContactMounted] = useState(false)
  const openContact = () => {
    setContactMounted(true)
    setContactOpen(true)
  }

  useFonts()
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
