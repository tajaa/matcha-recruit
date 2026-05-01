import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Calculator, ChevronRight } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import { PricingContactModal } from '../../../components/PricingContactModal'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type CalcCard = {
  to: string
  title: string
  description: string
  status: 'live' | 'soon'
}

const CALCS: CalcCard[] = [
  {
    to: '/resources/calculators/pto-accrual',
    title: 'PTO Accrual Calculator',
    description: 'Compute hourly accrual rate, per-paycheck PTO, and balance projections by tenure.',
    status: 'live',
  },
  {
    to: '/resources/calculators/turnover-cost',
    title: 'Turnover Cost Calculator',
    description: 'Estimate the true cost of voluntary turnover — recruiting, onboarding, productivity loss.',
    status: 'live',
  },
  {
    to: '/resources/calculators/overtime',
    title: 'Overtime Calculator',
    description: 'FLSA + state overtime — daily and weekly thresholds, regular-rate calculations.',
    status: 'soon',
  },
  {
    to: '/resources/calculators/total-comp',
    title: 'Total Compensation Calculator',
    description: 'Base + bonus + benefits + employer taxes + equity. Build a clean total-comp number.',
    status: 'soon',
  },
]

export default function Calculators({ embedded }: { embedded?: boolean }) {
  const [showPricing, setShowPricing] = useState(false)
  const root = embedded ? '/app/resources' : '/resources'

  useEffect(() => {
    document.title = 'HR Calculators — Matcha'
  }, [])

  return (
    <div style={{ backgroundColor: BG, color: INK, minHeight: embedded ? undefined : '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={`${embedded ? 'pt-6' : 'pt-28'} pb-20 max-w-[1100px] mx-auto px-6 sm:px-10`}>
        <nav className="flex items-center gap-2 text-xs mb-8" style={{ color: MUTED }}>
          <Link to={root} className="hover:opacity-60">Resources</Link>
          <ChevronRight className="w-3 h-3" />
          <span style={{ color: INK }}>Calculators</span>
        </nav>

        <header className="mb-14 max-w-2xl">
          <h1
            className="text-5xl sm:text-6xl tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            HR Calculators
          </h1>
          <p className="mt-4 text-base" style={{ color: MUTED }}>
            Quick, no-login math for the numbers you need most — accruals,
            turnover cost, overtime, total comp.
          </p>
        </header>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {CALCS.map(c => {
            const live = c.status === 'live'
            const Card = (
              <article
                className="p-6 rounded-2xl flex flex-col h-full"
                style={{ border: `1px solid ${LINE}`, opacity: live ? 1 : 0.6 }}
              >
                <div className="flex items-start justify-between mb-4">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center"
                    style={{ backgroundColor: 'rgba(15,15,15,0.05)' }}
                  >
                    <Calculator className="w-5 h-5" style={{ color: INK }} />
                  </div>
                  {live ? (
                    <ArrowUpRight className="w-4 h-4" style={{ color: MUTED }} />
                  ) : (
                    <span
                      className="text-[10px] tracking-wider px-2 py-1 rounded"
                      style={{ border: `1px solid ${LINE}`, color: MUTED }}
                    >
                      COMING SOON
                    </span>
                  )}
                </div>
                <h3
                  className="text-xl mb-2"
                  style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
                >
                  {c.title}
                </h3>
                <p className="text-sm" style={{ color: MUTED }}>
                  {c.description}
                </p>
              </article>
            )
            return live ? (
              <Link key={c.title} to={embedded ? `/app${c.to}` : c.to} className="block hover:opacity-80 transition-opacity">
                {Card}
              </Link>
            ) : (
              <div key={c.title}>{Card}</div>
            )
          })}
        </div>
      </main>

      {!embedded && <MarketingFooter />}
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}
