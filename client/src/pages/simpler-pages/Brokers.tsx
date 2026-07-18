import { useState } from 'react'
import { useSEO } from '../../hooks/useSEO'
import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { PricingContactModal } from '../../components/marketing/PricingContactModal'
import { BROKERS_JSON_LD } from './Brokers/data'
import { BG, INK } from './Brokers/theme'
import { Hero } from './Brokers/Hero'
import { Positioning } from './Brokers/Positioning'
import { PillarsGrid } from './Brokers/PillarsGrid'
import { ThePoint } from './Brokers/ThePoint'
import { CtaBand } from './Brokers/CtaBand'

// ---------------------------------------------------------------------------
// Simplified /brokers. Keeps the original colorful Book-Risk-Curve hero card
// (the signature the user wanted to preserve), then simplifies the rest into
// the simpler-pages design language: full-width alternating pillar rows with
// bespoke grayscale+green instruments, a coverage recap grid, an editorial
// cut, and the monochrome newsletter band.
// ---------------------------------------------------------------------------

export default function SimpleBrokersPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  useSEO({
    title: 'Matcha for Brokers | Book-of-Business Intelligence',
    description:
      "Give your P&C clients a live safety intake system — and get the intelligence layer back. Exposure-weighted risk curve, workers' comp loss control, and AI-drafted outreach across your whole book.",
    canonical: 'https://hey-matcha.com/matcha-brokers',
    jsonLd: BROKERS_JSON_LD,
  })

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} mode="consultation" />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onBookClick={() => setIsPricingOpen(true)} />

      <main>
        <Positioning />
        <PillarsGrid />
        <ThePoint />
      </main>

      <CtaBand onBookClick={() => setIsPricingOpen(true)} />
      <MarketingFooter newsletterVariant="matcha" />
    </div>
  )
}
