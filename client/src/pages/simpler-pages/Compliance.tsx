import { lazy, Suspense, useState } from 'react'

import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { useSEO } from '../../hooks/useSEO'
import { BONE, NOIR } from '../home/theme'
import { GrainOverlay, PageStyle, useMarketingNoir } from '../home/PageChrome'

import { Hero } from './Compliance/Hero'
import { Stakes } from './Compliance/Stakes'
import { OneSystem } from './Compliance/OneSystem'
import { Coverage } from './Compliance/Coverage'
import { PricingCalculator } from './Compliance/PricingCalculator'
import { ThePoint } from './Compliance/ThePoint'
import { CtaBand } from './Compliance/CtaBand'
import { COMPLIANCE_JSON_LD } from './Compliance/data'

// Second framer-motion importer on this route chunk alongside ComplianceInstrument
// — already lazy at App.tsx, so neither reaches the apex `/` chunk.
const PricingContactModal = lazy(() =>
  import('../../components/marketing/PricingContactModal').then((m) => ({
    default: m.PricingContactModal,
  })),
)

// ---------------------------------------------------------------------------
// Rebuilt onto the noir editorial surface (pages/home/*) — same product
// (jurisdictional compliance, handbook audit, policy management, credentialing)
// but with a claim in the hero instead of the product name, the enforcement
// data promoted from a scrolling ticker into a real section, one system
// section instead of two that repeated each other, and a self-serve funnel:
// live pricing → /compliance/signup. The fixed ComplianceTicker is dropped
// from this page only — it fights a transparent nav and restates the Stakes
// section below it; it stays mounted on the 6 other marketing pages that use it.
// ---------------------------------------------------------------------------

export default function SimpleCompliancePage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)
  const [hasOpenedPricing, setHasOpenedPricing] = useState(false)
  const openPricing = () => {
    setHasOpenedPricing(true)
    setIsPricingOpen(true)
  }

  useMarketingNoir()

  useSEO({
    title: 'Matcha Compliance — Multi-State Employment Compliance Monitoring',
    description:
      'Standalone multi-state employment compliance platform — jurisdiction tracking from federal to city, change alerts, handbook audits, policy management, and credentialing.',
    canonical: 'https://hey-matcha.com/matcha-compliance',
    jsonLd: COMPLIANCE_JSON_LD,
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
          <PricingContactModal
            isOpen={isPricingOpen}
            onClose={() => setIsPricingOpen(false)}
            mode="consultation"
          />
        </Suspense>
      )}

      <MarketingNav onDemoClick={openPricing} transparentAtTop />

      <Hero onContactClick={openPricing} />
      <Stakes />
      <OneSystem />
      <Coverage />
      <PricingCalculator onContactClick={openPricing} />
      <ThePoint />
      <CtaBand onContactClick={openPricing} />

      <div style={{ backgroundColor: BONE, color: 'var(--color-ivory-ink)' }}>
        <MarketingFooter newsletterVariant="matcha" />
      </div>
    </div>
  )
}
