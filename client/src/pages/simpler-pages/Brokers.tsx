import { lazy, Suspense, useState } from 'react'

import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { useSEO } from '../../hooks/useSEO'
import { BONE, NOIR } from '../home/theme'
import { GrainOverlay, PageStyle, useMarketingNoir } from '../home/PageChrome'

import { BROKERS_JSON_LD } from './Brokers/data'
import { Hero } from './Brokers/Hero'
import { Positioning } from './Brokers/Positioning'
import { PillarsGrid } from './Brokers/PillarsGrid'
import { ThePoint } from './Brokers/ThePoint'
import { CtaBand } from './Brokers/CtaBand'

const PricingContactModal = lazy(() =>
  import('../../components/marketing/PricingContactModal').then((m) => ({
    default: m.PricingContactModal,
  })),
)

// ---------------------------------------------------------------------------
// Rebuilt onto the noir editorial surface (pages/home/*), the same pass that
// already moved /matcha-compliance, /matcha-platform, and /matcha-lite. The
// hero's skeuomorphic "Book Risk Console" (charcoal chassis, physical knobs,
// recessed glass — see Brokers/console/) is UNCHANGED: it already sits in its
// own dark room, so it's visually compatible with the noir surface below it —
// the tonal step is now within one dark page rather than a cut against ivory.
// Positioning/PillarsGrid/ThePoint/CtaBand are re-tokened, with the three
// pillar instruments rebuilt on the shared noir InstrumentFrame. No pricing
// section here: unlike Compliance/Lite, broker relationships are sales-led,
// not self-serve Stripe, so there is no live price to calculate. ComplianceTicker
// is dropped from this page only, same as the other rebuilds.
// ---------------------------------------------------------------------------

export default function SimpleBrokersPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)
  const [hasOpenedPricing, setHasOpenedPricing] = useState(false)
  const openPricing = () => {
    setHasOpenedPricing(true)
    setIsPricingOpen(true)
  }

  useMarketingNoir()

  useSEO({
    title: 'Matcha for Brokers | Book-of-Business Intelligence',
    description:
      "Give your P&C clients a live safety intake system — and get the intelligence layer back. Exposure-weighted risk curve, workers' comp loss control, and AI-drafted outreach across your whole book.",
    canonical: 'https://hey-matcha.com/matcha-brokers',
    jsonLd: BROKERS_JSON_LD,
  })

  return (
    <div
      style={{ backgroundColor: NOIR, color: BONE }}
      className="home-root min-h-screen overflow-x-hidden"
    >
      <PageStyle />
      <GrainOverlay />

      {hasOpenedPricing && (
        <Suspense
          fallback={
            isPricingOpen ? (
              <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60">
                <div
                  className="h-8 w-8 animate-spin rounded-full border-2 border-white/25 border-t-white/90"
                  role="status"
                  aria-label="Loading"
                />
              </div>
            ) : null
          }
        >
          <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} mode="consultation" />
        </Suspense>
      )}

      <MarketingNav onDemoClick={openPricing} transparentAtTop />

      <Hero onBookClick={openPricing} />

      <main>
        <Positioning />
        <PillarsGrid />
        <ThePoint />
      </main>

      <CtaBand onBookClick={openPricing} />

      <div style={{ backgroundColor: BONE, color: 'var(--color-ivory-ink)' }}>
        <MarketingFooter newsletterVariant="matcha" />
      </div>
    </div>
  )
}
