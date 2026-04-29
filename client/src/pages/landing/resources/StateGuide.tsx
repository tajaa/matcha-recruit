import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronRight, ExternalLink } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import { PricingContactModal } from '../../../components/PricingContactModal'
import { api } from '../../../api/client'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type Requirement = {
  title: string
  summary: string | null
  current_value: string | null
  source_url: string | null
  source_name: string | null
  effective_date: string | null
  last_verified: string | null
  statute_citation: string | null
  canonical_key: string | null
}

type Category = {
  key: string
  label: string
  requirements: Requirement[]
}

type StateGuideResponse = {
  slug: string
  code: string
  name: string
  requirement_count: number
  last_verified: string | null
  categories: Category[]
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
        document.title = `${d.name} HR Compliance Guide — Matcha`
        const desc = document.querySelector('meta[name="description"]')
        if (desc) desc.setAttribute('content',
          `Wage, leave, paid sick time, final paycheck, and other HR compliance requirements for ${d.name}. ${d.requirement_count} requirements tracked.`)
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
            {data.name} HR Compliance Guide
          </h1>
          <p className="text-base" style={{ color: MUTED }}>
            {data.requirement_count} state-level requirements across {data.categories.length} categories.
            {data.last_verified && ` Last verified ${formatDate(data.last_verified)}.`}
          </p>
        </header>

        {data.categories.length > 1 && (
          <nav
            className="mb-10 p-4 rounded-xl flex flex-wrap gap-2"
            style={{ border: `1px solid ${LINE}` }}
          >
            {data.categories.map(cat => (
              <a
                key={cat.key}
                href={`#cat-${cat.key}`}
                className="text-xs px-3 py-1 rounded-full transition-opacity hover:opacity-60"
                style={{ color: INK, border: `1px solid ${LINE}` }}
              >
                {cat.label} <span style={{ color: MUTED }}>({cat.requirements.length})</span>
              </a>
            ))}
          </nav>
        )}

        {data.categories.map(cat => (
          <section key={cat.key} id={`cat-${cat.key}`} className="mb-12 scroll-mt-28">
            <h2
              className="text-3xl mb-6 pb-3"
              style={{
                fontFamily: DISPLAY,
                color: INK,
                fontWeight: 500,
                borderBottom: `1px solid ${LINE}`,
              }}
            >
              {cat.label}
            </h2>
            <div className="flex flex-col gap-4">
              {cat.requirements.map((req, i) => (
                <article
                  key={`${cat.key}-${i}`}
                  className="p-5 rounded-xl"
                  style={{ border: `1px solid ${LINE}` }}
                >
                  <h3
                    className="text-base mb-2"
                    style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
                  >
                    {req.title}
                  </h3>
                  {req.current_value && (
                    <p className="text-sm font-mono mb-2" style={{ color: INK }}>
                      <span style={{ color: MUTED }}>Current:</span> {req.current_value}
                    </p>
                  )}
                  {req.summary && (
                    <p className="text-sm mb-3" style={{ color: MUTED }}>
                      {req.summary}
                    </p>
                  )}
                  <div className="flex flex-wrap items-center gap-3 text-xs" style={{ color: MUTED }}>
                    {req.statute_citation && (
                      <span>
                        <span style={{ opacity: 0.7 }}>Statute:</span> {req.statute_citation}
                      </span>
                    )}
                    {req.effective_date && (
                      <span>
                        <span style={{ opacity: 0.7 }}>Effective:</span> {formatDate(req.effective_date)}
                      </span>
                    )}
                    {req.source_url && (
                      <a
                        href={req.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 hover:opacity-60"
                        style={{ color: INK }}
                      >
                        {req.source_name ?? 'Source'} <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))}

        <section
          className="p-8 rounded-2xl"
          style={{ border: `1px solid ${LINE}`, backgroundColor: 'rgba(15,15,15,0.03)' }}
        >
          <h2 className="text-2xl mb-3" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
            Get a tailored compliance scan for your business
          </h2>
          <p className="text-sm mb-6 max-w-2xl" style={{ color: MUTED }}>
            Matcha checks your locations, headcount, and industry against
            the {data.requirement_count}+ state requirements above — plus
            local ordinances in cities and counties — and tells you exactly
            what's missing.
          </p>
          <button
            onClick={() => setShowPricing(true)}
            className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
            style={{ backgroundColor: INK, color: BG }}
          >
            See Matcha →
          </button>
        </section>
      </main>

      <MarketingFooter />
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}
