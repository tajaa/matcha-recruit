import { useState } from 'react'

import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { PricingContactModal } from '../../components/marketing/PricingContactModal'

import { Hero } from './Compliance/Hero'
import { PillarsGrid } from './Compliance/PillarsGrid'
import { CoverageGrid } from './Compliance/CoverageGrid'
import { ThePoint } from './Compliance/ThePoint'
import { CtaBand } from './Compliance/CtaBand'
import { BG, INK } from './Compliance/theme'

// ---------------------------------------------------------------------------
// Simplified /compliance — same four-pillar product (jurisdictional
// compliance, handbook audit, policy management, credentialing) as the full
// page, told in outcome-level marketing copy only. No mechanism detail (no
// "preemption engine", no AI/OCR specifics, no data provenance) and no
// in-app mockups.
//
// Grayscale card system, one green accent used the same way on every card:
// it marks the single node each pillar resolves to — the governing rule,
// the critical gap, the active policy, the day a credential expires. That's
// the "shape strip", a chip row that traces each pillar's real structure
// instead of a generic bullet icon.
// ---------------------------------------------------------------------------

export default function SimpleCompliancePage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} mode="consultation" />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onContactClick={() => setIsPricingOpen(true)} />

      <main>
        <PillarsGrid />
        <CoverageGrid />
        <ThePoint />
      </main>

      <CtaBand onContactClick={() => setIsPricingOpen(true)} />
      <MarketingFooter newsletterVariant="matcha" />
    </div>
  )
}
