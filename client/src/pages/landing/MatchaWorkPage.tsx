import { useState } from 'react'

import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { PricingContactModal } from '../../components/marketing/PricingContactModal'
import { INK, BG } from './MatchaWorkPage/constants'
import { PILLARS } from './MatchaWorkPage/data'
import { Hero } from './MatchaWorkPage/Hero'
import { ProductPillar } from './MatchaWorkPage/ProductPillar'
import { BetaWaitlistCta } from './MatchaWorkPage/BetaWaitlistCta'
import { ClosingCta } from './MatchaWorkPage/ClosingCta'

export default function MatchaWorkPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero />

      <main>
        {PILLARS.map((pillar, i) => (
          <ProductPillar key={pillar.id} pillar={pillar} reverse={i % 2 === 1} />
        ))}
        <BetaWaitlistCta />
        <ClosingCta onPricingClick={() => setIsPricingOpen(true)} />
      </main>

      <MarketingFooter />
    </div>
  )
}
