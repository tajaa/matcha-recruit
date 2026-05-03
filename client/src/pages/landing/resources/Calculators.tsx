import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Calculator, ChevronRight } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import NewsletterSignup from '../../../components/NewsletterSignup'
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
    status: 'live',
  },
  {
    to: '/resources/calculators/total-comp',
    title: 'Total Compensation Calculator',
    description: 'Base + bonus + benefits + employer taxes + equity. Build a clean total-comp number.',
    status: 'live',
  },
]

function mkT(embedded?: boolean) {
  return embedded ? {
    ink: '#e4e4e7', bg: 'transparent', muted: '#71717a',
    line: '#3f3f46', display: 'inherit',
    iconBg: '#27272a',
  } : {
    ink: INK, bg: BG, muted: MUTED,
    line: LINE, display: DISPLAY,
    iconBg: 'rgba(15,15,15,0.05)',
  }
}

export default function Calculators({ embedded }: { embedded?: boolean }) {
  const [showPricing, setShowPricing] = useState(false)
  const root = embedded ? '/app/resources' : '/resources'
  const t = mkT(embedded)

  useEffect(() => {
    document.title = 'HR Calculators — Matcha'
  }, [])

  return (
    <div style={embedded ? { color: t.ink } : { backgroundColor: t.bg, color: t.ink, minHeight: '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={embedded ? '' : 'pt-28 pb-20 max-w-[1100px] mx-auto px-6 sm:px-10'}>
        <nav className={`flex items-center gap-2 text-xs mb-8 ${embedded ? 'text-vsc-text/40' : ''}`} style={embedded ? undefined : { color: t.muted }}>
          <Link to={root} className={embedded ? 'hover:text-vsc-text/70 transition-colors' : 'hover:opacity-60'}>Resources</Link>
          <ChevronRight className={`w-3 h-3 ${embedded ? 'text-vsc-text/20' : ''}`} />
          <span className={embedded ? 'text-vsc-text/60' : ''} style={embedded ? undefined : { color: t.ink }}>Calculators</span>
        </nav>

        <header className="mb-14 max-w-2xl">
          <h1
            className={embedded ? "text-2xl font-semibold text-vsc-text" : "text-5xl sm:text-6xl tracking-tight"}
            style={embedded ? undefined : { fontFamily: t.display, fontWeight: 500, color: t.ink }}
          >
            HR Calculators
          </h1>
          <p className={`mt-4 text-base ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>
            Quick, no-login math for the numbers you need most — accruals,
            turnover cost, overtime, total comp.
          </p>
        </header>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {CALCS.map(c => {
            const live = c.status === 'live'
            const Card = (
              <article
                className={embedded
                  ? 'p-6 rounded-xl flex flex-col h-full border border-vsc-border bg-vsc-panel'
                  : 'p-6 rounded-2xl flex flex-col h-full'}
                style={embedded ? { opacity: live ? 1 : 0.6 } : { border: `1px solid ${t.line}`, opacity: live ? 1 : 0.6 }}
              >
                <div className="flex items-start justify-between mb-4">
                  <div
                    className={`w-10 h-10 rounded-lg flex items-center justify-center ${embedded ? 'bg-vsc-bg' : ''}`}
                    style={embedded ? undefined : { backgroundColor: t.iconBg }}
                  >
                    <Calculator className={`w-5 h-5 ${embedded ? 'text-vsc-text' : ''}`} style={embedded ? undefined : { color: t.ink }} />
                  </div>
                  {live ? (
                    <ArrowUpRight className={`w-4 h-4 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }} />
                  ) : (
                    <span
                      className={`text-[10px] tracking-wider px-2 py-1 rounded ${embedded ? 'border border-vsc-border text-vsc-text/40' : ''}`}
                      style={embedded ? undefined : { border: `1px solid ${t.line}`, color: t.muted }}
                    >
                      COMING SOON
                    </span>
                  )}
                </div>
                <h3
                  className={embedded ? 'text-xl font-semibold text-vsc-text mb-2' : 'text-xl mb-2'}
                  style={embedded ? undefined : { fontFamily: t.display, color: t.ink, fontWeight: 500 }}
                >
                  {c.title}
                </h3>
                <p className={embedded ? 'text-sm text-vsc-text/50' : 'text-sm'} style={embedded ? undefined : { color: t.muted }}>
                  {c.description}
                </p>
              </article>
            )
            return live ? (
              <Link key={c.title} to={embedded ? `/app${c.to}` : c.to} className={embedded ? 'block hover:border-vsc-text/30 transition-colors' : 'block hover:opacity-80 transition-opacity'}>
                {Card}
              </Link>
            ) : (
              <div key={c.title}>{Card}</div>
            )
          })}
        </div>

        {!embedded && (
          <section className="mt-14 max-w-xl mx-auto">
            <NewsletterSignup
              source="calculators"
              variant="card"
              headline="Get the next calc when it ships."
              description="We add a calculator every couple weeks. Subscribe to know when."
            />
          </section>
        )}
      </main>

      {!embedded && <MarketingFooter />}
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}
