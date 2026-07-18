import { useState } from 'react'

import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { PricingContactModal } from '../../components/marketing/PricingContactModal'

import { BG, INK } from './Lite/constants'
import { Hero } from './Lite/Hero'
import { PillarsGrid } from './Lite/PillarsGrid'
import { CoverageGrid } from './Lite/CoverageGrid'
import { CtaBand } from './Lite/CtaBand'

// ---------------------------------------------------------------------------
// Simplified /matcha-daily (Matcha Lite). Outcome-level marketing copy, the
// simpler-pages design language: clean centered hero, four full-width
// alternating pillar rows with bespoke grayscale+green instruments, a
// coverage recap grid, an editorial cut, and the monochrome newsletter band.
// ---------------------------------------------------------------------------

export default function SimpleLitePage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onContactClick={() => setIsPricingOpen(true)} />

      <main>
        <PillarsGrid />
        <CoverageGrid />
      </main>

      <CtaBand onContactClick={() => setIsPricingOpen(true)} />
      <MarketingFooter newsletterVariant="matcha" />
    </div>
  )
}
