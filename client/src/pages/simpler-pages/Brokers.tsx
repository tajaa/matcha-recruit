import { lazy, Suspense, useState } from 'react'

import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { useSEO } from '../../hooks/useSEO'
import { BONE, NOIR } from '../home/theme'
import { GrainOverlay, PageStyle, useMarketingNoir } from '../home/PageChrome'

import { BROKERS_JSON_LD } from './Brokers/data'
import { Hero } from './Brokers/Hero'
import { Positioning } from './Brokers/Positioning'
import { MoneyBand } from './Brokers/MoneyBand'
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
// hero now shares that exact skeleton too — left-aligned copy + right-column
// InstrumentFrame instrument (Brokers/BookInstrument.tsx) — replacing the old
// skeuomorphic "Book Risk Console" (charcoal chassis, physical knobs, its own
// materials system under Brokers/console/, now deleted): it needed a
// non-wrapping ~700px module rack and never fit this column, so it read as a
// different product from the rest of the page. Its curve is now a legible
// miniature of the real /broker/risk-curve chart (dollar axis, Expected +
// PML 99% reference lines) and its account rows use the real Accounts-table
// status vocabulary (Healthy/Watch/At Risk) driven off `row.band`, not the
// cycling index — the original coupled them wrong and could show a red dot
// reading "Stable". Positioning/PillarsGrid/ThePoint/CtaBand are re-tokened;
// PillarsGrid grew from 3 to 5 rows (added Submission Packet + Broker Pilot,
// two real features the page previously never mentioned), and MoneyBand adds
// the page's first dollar figures (Premium Δ, Est. commission, adverse
// development) pulled from the product's own strongest money statements,
// each carrying its own "directional, not a quote" caveat. No pricing
// section here: unlike Compliance/Lite, broker relationships are sales-led,
// not self-serve Stripe, so there is no live price to calculate.
// ComplianceTicker is dropped from this page only, same as the other
// rebuilds.
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
        <MoneyBand />
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
