import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronRight, Lock } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import { PricingContactModal } from '../../../components/PricingContactModal'
import { api } from '../../../api/client'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type CategoryPreview = {
  key: string
  label: string
  count: number
  sample_titles: string[]
  preview_value: string | null
}

type StateGuideResponse = {
  slug: string
  code: string
  name: string
  requirement_count: number
  category_count: number
  last_verified: string | null
  categories: CategoryPreview[]
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  } catch {
    return iso
  }
}

export default function StateGuide() {
  const { slug } = useParams<{ slug: string }>()
  const [data, setData] = useState<StateGuideResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showPricing, setShowPricing] = useState(false)

  useEffect(() => {
    if (!slug) return
    setLoading(true)
    api.get<StateGuideResponse>(`/resources/state-guides/${slug}`)
      .then(d => {
        setData(d)
        document.title = `${d.name} HR Compliance Overview — Matcha`
        const desc = document.querySelector('meta[name="description"]')
        if (desc) desc.setAttribute('content',
          `Overview of ${d.requirement_count}+ ${d.name} HR compliance requirements across ${d.category_count} categories — wage, leave, paid sick time, final paycheck, and more.`)
      })
      .catch(err => setError(err?.message ?? 'Failed to load'))
      .finally(() => setLoading(false))
  }, [slug])

  if (loading) {
    return (
      <div style={{ backgroundColor: BG, color: INK, minHeight: '100vh' }}>
        <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />
        <main className="pt-28 max-w-[900px] mx-auto px-6"><p style={{ color: MUTED }}>Loading…</p></main>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div style={{ backgroundColor: BG, color: INK, minHeight: '100vh' }}>
        <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />
        <main className="pt-28 pb-20 max-w-[700px] mx-auto px-6 sm:px-10 text-center">
          <h1 className="text-3xl mb-4" style={{ fontFamily: DISPLAY, color: INK }}>
            State guide unavailable
          </h1>
          <p className="mb-6" style={{ color: MUTED }}>
            {error ?? `We don't have data for "${slug}" yet.`}
          </p>
          <Link
            to="/resources/states"
            className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
            style={{ backgroundColor: INK, color: BG }}
          >
            Browse all states
          </Link>
        </main>
        <MarketingFooter />
        <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
      </div>
    )
  }

  return (
    <div style={{ backgroundColor: BG, color: INK, minHeight: '100vh' }}>
      <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />

      <main className="pt-28 pb-20 max-w-[900px] mx-auto px-6 sm:px-10">
        <nav className="flex items-center gap-2 text-xs mb-8 flex-wrap" style={{ color: MUTED }}>
          <Link to="/resources" className="hover:opacity-60">Resources</Link>
          <ChevronRight className="w-3 h-3" />
          <Link to="/resources/states" className="hover:opacity-60">State Guides</Link>
          <ChevronRight className="w-3 h-3" />
          <span style={{ color: INK }}>{data.name}</span>
        </nav>

        <header className="mb-10">
          <span
            className="inline-block text-[10px] tracking-wider px-2 py-1 rounded mb-4"
            style={{ border: `1px solid ${LINE}`, color: MUTED }}
          >
            {data.code} — STATE-LEVEL
          </span>
          <h1
            className="text-5xl sm:text-6xl tracking-tight mb-3"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            {data.name} HR Compliance Overview
          </h1>
          <p className="text-base" style={{ color: MUTED }}>
            We track <strong style={{ color: INK }}>{data.requirement_count} state-level requirements</strong> across <strong style={{ color: INK }}>{data.category_count} compliance categories</strong> in {data.name}.
            {data.last_verified && ` Last verified ${formatDate(data.last_verified)}.`}
          </p>
        </header>

        <section
          className="mb-10 p-6 rounded-2xl"
          style={{ border: `1px solid ${LINE}`, backgroundColor: 'rgba(15,15,15,0.03)' }}
        >
          <p className="text-sm" style={{ color: INK }}>
            <strong>This is a free overview.</strong>{' '}
            <span style={{ color: MUTED }}>
              Full requirement details — current values, source statutes,
              effective dates, employer-action steps, and city/county
              ordinances on top of state law — are available inside Matcha.
            </span>
          </p>
        </section>

        <h2
          className="text-2xl mb-6"
          style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
        >
          Categories tracked in {data.name}
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-12">
          {data.categories.map(cat => (
            <article
              key={cat.key}
              className="p-5 rounded-xl"
              style={{ border: `1px solid ${LINE}` }}
            >
              <div className="flex items-baseline justify-between mb-3 gap-2">
                <h3
                  className="text-base"
                  style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
                >
                  {cat.label}
                </h3>
                <span
                  className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded whitespace-nowrap"
                  style={{ border: `1px solid ${LINE}`, color: MUTED }}
                >
                  {cat.count} {cat.count === 1 ? 'rule' : 'rules'}
                </span>
              </div>

              {cat.preview_value && (
                <p
                  className="text-sm font-mono mb-3 px-3 py-2 rounded"
                  style={{ color: INK, backgroundColor: 'rgba(15,15,15,0.04)' }}
                >
                  {cat.preview_value}
                </p>
              )}

              {cat.sample_titles.length > 0 && (
                <ul className="text-xs flex flex-col gap-1 mb-3" style={{ color: MUTED }}>
                  {cat.sample_titles.map((t, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span style={{ opacity: 0.5 }}>·</span>
                      <span>{t}</span>
                    </li>
                  ))}
                  {cat.count > cat.sample_titles.length && (
                    <li
                      className="flex items-center gap-1.5 mt-1"
                      style={{ color: INK, opacity: 0.7 }}
                    >
                      <Lock className="w-3 h-3" />
                      <span>+ {cat.count - cat.sample_titles.length} more in Matcha</span>
                    </li>
                  )}
                </ul>
              )}
            </article>
          ))}
        </div>

        <section
          className="p-8 rounded-2xl"
          style={{ border: `1px solid ${LINE}`, backgroundColor: 'rgba(15,15,15,0.03)' }}
        >
          <h2 className="text-2xl mb-3" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
            Get the full {data.name} compliance breakdown
          </h2>
          <p className="text-sm mb-6 max-w-2xl" style={{ color: MUTED }}>
            Inside Matcha you get every requirement above with current
            values, statute citations, source links, employer-action
            steps, last-changed dates, plus city and county ordinances
            for {data.name}. Run a tailored scan against your locations,
            headcount, and industry — see exactly what's missing.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link
              to="/auth/resources-signup"
              className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
              style={{ backgroundColor: INK, color: BG }}
            >
              Create free account →
            </Link>
            <Link
              to="/resources/audit"
              className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
              style={{ border: `1px solid ${LINE}`, color: INK }}
            >
              Free compliance audit
            </Link>
            <button
              onClick={() => setShowPricing(true)}
              className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
              style={{ border: `1px solid ${LINE}`, color: INK, opacity: 0.7 }}
            >
              Talk to sales
            </button>
          </div>
        </section>
      </main>

      <MarketingFooter />
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}
