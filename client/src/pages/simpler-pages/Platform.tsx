import { useState } from 'react'

import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { PricingContactModal } from '../../components/marketing/PricingContactModal'

import { Hero } from './Platform/Hero'
import { PillarsGrid } from './Platform/PillarsGrid'
import { ThePoint } from './Platform/ThePoint'
import { CtaBand } from './Platform/CtaBand'
import { BG, INK } from './Platform/theme'

// ---------------------------------------------------------------------------
// Simplified /platform — the full Matcha platform (EHS + GRC + ER unified on
// one agentic brain) told in outcome-level marketing copy only. No mechanism
// detail, no dense product dashboards — the same design language as the
// simplified /matcha-compliance page: a live hero panel, four full-width
// alternating pillar rows each with a bespoke grayscale+green instrument, a
// coverage recap grid, an editorial cut, and the monochrome newsletter band.
// ---------------------------------------------------------------------------

export default function SimplePlatformPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onContactClick={() => setIsPricingOpen(true)} />

      <main>
        <PillarsGrid />
        <ThePoint />
      </main>

      <CtaBand onContactClick={() => setIsPricingOpen(true)} />
      <MarketingFooter newsletterVariant="matcha" />
    </div>
  )
}
