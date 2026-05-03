import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, FileText, Lock } from 'lucide-react'

import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import NewsletterSignup from '../../components/NewsletterSignup'
import { PricingContactModal } from '../../components/PricingContactModal'
import { useMe } from '../../hooks/useMe'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type Category = {
  to: string
  title: string
  description: string
  status: 'live' | 'soon'
  gated: boolean
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>
}

const CATEGORIES: Category[] = [
  {
    to: '/resources/glossary',
    title: 'HR Glossary',
    description:
      'Plain-English definitions for FLSA, ACA, FMLA, COBRA, and the alphabet soup of HR.',
    status: 'live',
    gated: false,
    icon: FileText,
  },
  {
    to: '/resources/templates',
    title: 'Templates',
    description:
      '14 editable HR templates — offer letters, PIPs, termination checklists, interview scorecards, and more.',
    status: 'live',
    gated: true,
    icon: FileText,
  },
  {
    to: '/resources/calculators',
    title: 'Calculators',
    description:
      'PTO accrual, salary benchmarks, turnover cost, overtime — interactive HR calculators.',
    status: 'live',
    gated: true,
    icon: FileText,
  },
  {
    to: '/resources/audit',
    title: 'Compliance Audit',
    description:
      '12 questions → a tailored compliance gap report for your state, headcount, and industry.',
    status: 'live',
    gated: true,
    icon: FileText,
  },
  {
    to: '/resources/states',
    title: 'State Compliance Guides',
    description:
      'A page per state covering posters, min wage, sick leave, final paycheck, and pay transparency.',
    status: 'soon',
    gated: true,
    icon: FileText,
  },
  {
    to: '/blog',
    title: 'Blog',
    description:
      'Field notes from the practice — HR, compliance, GRC, and people-ops.',
    status: 'live',
    gated: false,
    icon: FileText,
  },
]

export default function ResourcesHub() {
  const [showPricing, setShowPricing] = useState(false)
  const { me, loading } = useMe()
  const isSignedIn = !!me && me.user.role === 'client'
  // While auth resolves, hide gated cards rather than flashing them then
  // hiding them once `me` resolves. Show them once we know auth state.
  const showGated = !loading && isSignedIn

  // Guests only see ungated resources (glossary + blog). Signed-in clients
  // see the full catalog.
  const visible = CATEGORIES.filter(c => !c.gated || showGated)

  return (
    <div style={{ backgroundColor: BG, color: INK, minHeight: '100vh' }}>
      <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />

      <main className="pt-28 pb-20 max-w-[1100px] mx-auto px-6 sm:px-10">
        <header className="mb-14 max-w-2xl">
          <h1
            className="text-5xl sm:text-6xl tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            HR Resource Center
          </h1>
          <p className="mt-4 text-base" style={{ color: MUTED }}>
            Free templates, calculators, the compliance audit, and answers
            to the questions HR teams Google a hundred times a year.
            {!loading && !isSignedIn && (
              <>
                {' '}A free business account unlocks templates, calculators,
                state guides, and the compliance audit —{' '}
                <Link to="/auth/resources-signup" className="underline" style={{ color: INK }}>sign up</Link>.
              </>
            )}
          </p>
        </header>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {visible.map(cat => {
            const Icon = cat.icon
            const live = cat.status === 'live'
            const Card = (
              <article
                className="p-6 rounded-2xl flex flex-col h-full transition-opacity"
                style={{
                  border: `1px solid ${LINE}`,
                  opacity: live ? 1 : 0.6,
                }}
              >
                <div className="flex items-start justify-between mb-4">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center"
                    style={{ backgroundColor: 'rgba(15,15,15,0.05)' }}
                  >
                    <Icon className="w-5 h-5" style={{ color: INK }} />
                  </div>
                  {!live ? (
                    <span
                      className="text-[10px] tracking-wider px-2 py-1 rounded"
                      style={{ border: `1px solid ${LINE}`, color: MUTED }}
                    >
                      COMING SOON
                    </span>
                  ) : (
                    <ArrowUpRight className="w-4 h-4" style={{ color: MUTED }} />
                  )}
                </div>
                <h3
                  className="text-xl mb-2"
                  style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
                >
                  {cat.title}
                </h3>
                <p className="text-sm" style={{ color: MUTED }}>
                  {cat.description}
                </p>
              </article>
            )

            if (!live) {
              return <div key={cat.title}>{Card}</div>
            }
            return (
              <Link key={cat.title} to={cat.to} className="block hover:opacity-80 transition-opacity">
                {Card}
              </Link>
            )
          })}

          {!loading && !isSignedIn && (
            <Link
              to="/auth/resources-signup"
              className="block hover:opacity-80 transition-opacity"
            >
              <article
                className="p-6 rounded-2xl flex flex-col h-full"
                style={{ border: `1px dashed ${LINE}`, backgroundColor: 'rgba(15,15,15,0.02)' }}
              >
                <div className="flex items-start justify-between mb-4">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center"
                    style={{ backgroundColor: 'rgba(15,15,15,0.05)' }}
                  >
                    <Lock className="w-5 h-5" style={{ color: INK }} />
                  </div>
                  <ArrowUpRight className="w-4 h-4" style={{ color: MUTED }} />
                </div>
                <h3
                  className="text-xl mb-2"
                  style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
                >
                  Unlock the full library
                </h3>
                <p className="text-sm" style={{ color: MUTED }}>
                  Templates, calculators, state guides, and the compliance
                  audit are gated to free business accounts. Takes 30 seconds.
                </p>
              </article>
            </Link>
          )}
        </div>

        <section className="mt-16 max-w-2xl mx-auto">
          <NewsletterSignup
            source="resources_hub"
            variant="card"
            headline="One brief a week."
            description="Employment-law changes, compliance gotchas, and the occasional template."
          />
        </section>
      </main>

      <MarketingFooter />
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}
