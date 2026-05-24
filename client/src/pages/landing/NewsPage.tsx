import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { HRNewsSection } from '../../components/landing/HRNewsSection'

export default function NewsPage() {
  return (
    <div style={{ backgroundColor: 'var(--color-ivory-bg)', color: 'var(--color-ivory-ink)' }} className="min-h-screen">
      <ComplianceTicker />
      <MarketingNav />
      <main>
        <HRNewsSection />
      </main>
      <MarketingFooter />
    </div>
  )
}
