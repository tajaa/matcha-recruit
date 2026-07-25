import { lazy, Suspense, useState } from 'react'

import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { useSEO } from '../../hooks/useSEO'
import { BONE, NOIR } from '../home/theme'
import { GrainOverlay, PageStyle, useMarketingNoir } from '../home/PageChrome'

import { Hero } from './Lite/Hero'
import { PillarsGrid } from './Lite/PillarsGrid'
import { PricingCalculator } from './Lite/PricingCalculator'
import { ThePoint } from './Lite/ThePoint'
import { CtaBand } from './Lite/CtaBand'
import { LITE_JSON_LD } from './Lite/data'

const PricingContactModal = lazy(() =>
  import('../../components/marketing/PricingContactModal').then((m) => ({
    default: m.PricingContactModal,
  })),
)

// ---------------------------------------------------------------------------
// Rebuilt onto the noir editorial surface (pages/home/*), the same pass that
// already moved /matcha-compliance and /matcha-platform. The old CoverageGrid
// (5 cards, 4 of which restated the 4 pillars) is folded down to the one card
// that wasn't a repeat; a live Pricing section (headcount + Lite/Essentials
// toggle) replaces the "Talk to sales"-only funnel — Matcha Lite is self-serve
// Stripe and this page never linked /lite/signup before. Hero swaps the old
// lazy RiskInsightsHero (recharts + d3, no other importers) for home's
// statically-imported DailyInstrument; OshaLogInstrument moves from a buggy
// local OSHA tile (unclamped useCountUp — same defect removed from
// Platform/hooks.ts) to pillar 04, lazy since it's below the fold.
// ComplianceTicker is dropped from this page only, same as the other rebuilds.
// ---------------------------------------------------------------------------

export default function SimpleLitePage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)
  const [hasOpenedPricing, setHasOpenedPricing] = useState(false)
  const openPricing = () => {
    setHasOpenedPricing(true)
    setIsPricingOpen(true)
  }

  useMarketingNoir()

  useSEO({
    title: 'Matcha Lite — Incident Reporting, OSHA Logs & HR Records for Small Teams',
    description:
      'The everyday intake layer for small teams — magic-link incident reporting, HRIS/CSV roster import, IR pattern analysis, and self-updating OSHA 300 logs.',
    canonical: 'https://hey-matcha.com/matcha-lite',
    jsonLd: LITE_JSON_LD,
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
        <PricingCalculator onContactClick={openPricing} />
        <ThePoint />
      </main>

      <CtaBand onContactClick={openPricing} />

      <div style={{ backgroundColor: BONE, color: 'var(--color-ivory-ink)' }}>
        <MarketingFooter newsletterVariant="matcha" />
      </div>
    </div>
  )
}
