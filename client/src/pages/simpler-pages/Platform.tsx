import { lazy, Suspense, useState } from 'react'

import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { useSEO } from '../../hooks/useSEO'
import { BONE, NOIR } from '../home/theme'
import { GrainOverlay, PageStyle, useMarketingNoir } from '../home/PageChrome'

import { Hero } from './Platform/Hero'
import { PillarsGrid } from './Platform/PillarsGrid'
import { ThePoint } from './Platform/ThePoint'
import { CtaBand } from './Platform/CtaBand'
import { PLATFORM_JSON_LD } from './Platform/data'

const PricingContactModal = lazy(() =>
  import('../../components/marketing/PricingContactModal').then((m) => ({
    default: m.PricingContactModal,
  })),
)

// ---------------------------------------------------------------------------
// Rebuilt onto the noir editorial surface (pages/home/*), the same pass that
// already moved /matcha-compliance. Unlike Compliance this page had no
// duplicated section — the four alternating pillar rows are kept, re-tokened,
// with their instruments rebuilt on the shared noir InstrumentFrame. The hero
// swaps the old lazy 600px AgentReasoningAnimation panel (an LCP hazard above
// the fold) for home's statically-imported PlatformInstrument; the reasoning
// animation moves to pillar 04 ("One Brain"), where it's actually the point,
// and stays lazy there since it's below the fold. ComplianceTicker is dropped
// from this page only, same as Compliance — it fights a transparent nav.
// ---------------------------------------------------------------------------

export default function SimplePlatformPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)
  const [hasOpenedPricing, setHasOpenedPricing] = useState(false)
  const openPricing = () => {
    setHasOpenedPricing(true)
    setIsPricingOpen(true)
  }

  useMarketingNoir()

  useSEO({
    title: 'Matcha Full Platform — Safety, Compliance & Employee Relations, Unified',
    description:
      'Safety, compliance, and employee relations unified on one agentic platform — every signal informs the others, rolled into a single live risk index.',
    canonical: 'https://hey-matcha.com/matcha-platform',
    jsonLd: PLATFORM_JSON_LD,
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
          <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
        </Suspense>
      )}

      <MarketingNav onDemoClick={openPricing} transparentAtTop />

      <Hero onContactClick={openPricing} />

      <main>
        <PillarsGrid />
        <ThePoint />
      </main>

      <CtaBand onContactClick={openPricing} />

      <div style={{ backgroundColor: BONE, color: 'var(--color-ivory-ink)' }}>
        <MarketingFooter newsletterVariant="matcha" />
      </div>
    </div>
  )
}
