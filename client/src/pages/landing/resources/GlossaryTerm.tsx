import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import { PricingContactModal } from '../../../components/PricingContactModal'
import { GLOSSARY, CATEGORIES_LABEL } from './glossaryData'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

export default function GlossaryTerm({ embedded }: { embedded?: boolean }) {
  const { slug } = useParams<{ slug: string }>()
  const [showPricing, setShowPricing] = useState(false)
  const root = embedded ? '/app/resources' : '/resources'

  const term = useMemo(() => GLOSSARY.find(t => t.slug === slug), [slug])
  const related = useMemo(
    () => (term?.related ?? []).map(s => GLOSSARY.find(t => t.slug === s)).filter(Boolean) as typeof GLOSSARY,
    [term],
  )

  useEffect(() => {
    if (term) {
      document.title = `${term.abbreviation ?? term.term} — HR Glossary | Matcha`
      const desc = document.querySelector('meta[name="description"]')
      if (desc) desc.setAttribute('content', term.short)
    }
  }, [term])

  if (!term) {
    return (
      <div style={{ backgroundColor: BG, color: INK, minHeight: embedded ? undefined : '100vh' }}>
        {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}
        <main className={`${embedded ? 'pt-6' : 'pt-28'} pb-20 max-w-[700px] mx-auto px-6 sm:px-10 text-center`}>
          <h1 className="text-3xl mb-4" style={{ fontFamily: DISPLAY, color: INK }}>
            Term not found
          </h1>
          <p className="mb-6" style={{ color: MUTED }}>
            We don't have a definition for "{slug}" yet.
          </p>
          <Link
            to={`${root}/glossary`}
            className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
            style={{ backgroundColor: INK, color: BG }}
          >
            Browse all terms
          </Link>
        </main>
        {!embedded && <MarketingFooter />}
        <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
      </div>
    )
  }

  return (
    <div style={{ backgroundColor: BG, color: INK, minHeight: embedded ? undefined : '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={`${embedded ? 'pt-6' : 'pt-28'} pb-20 max-w-[760px] mx-auto px-6 sm:px-10`}>
        <nav className="flex items-center gap-2 text-xs mb-8 flex-wrap" style={{ color: MUTED }}>
          <Link to={root} className="hover:opacity-60">Resources</Link>
          <ChevronRight className="w-3 h-3" />
          <Link to={`${root}/glossary`} className="hover:opacity-60">Glossary</Link>
          <ChevronRight className="w-3 h-3" />
          <span style={{ color: INK }}>{term.abbreviation ?? term.term}</span>
        </nav>

        <header className="mb-10">
          <span
            className="inline-block text-[10px] tracking-wider px-2 py-1 rounded mb-4"
            style={{ border: `1px solid ${LINE}`, color: MUTED }}
          >
            {CATEGORIES_LABEL[term.category].toUpperCase()}
          </span>
          <h1
            className="text-4xl sm:text-5xl tracking-tight mb-3"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            {term.abbreviation ?? term.term}
          </h1>
          {term.abbreviation && (
            <p className="text-xl mb-2" style={{ color: MUTED, fontFamily: DISPLAY }}>
              {term.term}
            </p>
          )}
          <p className="text-lg mt-4" style={{ color: INK, opacity: 0.8 }}>
            {term.short}
          </p>
        </header>

        <article
          className="text-base leading-relaxed mb-12"
          style={{ color: INK, opacity: 0.85 }}
        >
          {term.definition.split('\n').map((para, i) => (
            <p key={i} className="mb-4">{para}</p>
          ))}
        </article>

        {related.length > 0 && (
          <section className="mb-12">
            <h2
              className="text-sm tracking-wider mb-4 uppercase"
              style={{ color: MUTED }}
            >
              Related Terms
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {related.map(r => (
                <Link
                  key={r.slug}
                  to={`${root}/glossary/${r.slug}`}
                  className="p-4 rounded-xl block transition-opacity hover:opacity-80"
                  style={{ border: `1px solid ${LINE}` }}
                >
                  <div
                    className="text-base mb-1"
                    style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
                  >
                    {r.abbreviation ?? r.term}
                  </div>
                  <div className="text-xs" style={{ color: MUTED }}>
                    {r.short}
                  </div>
                </Link>
              ))}
            </div>
          </section>
        )}

        <section
          className="p-8 rounded-2xl"
          style={{ border: `1px solid ${LINE}`, backgroundColor: 'rgba(15,15,15,0.03)' }}
        >
          <h2 className="text-xl mb-3" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
            Stop guessing. Get state-specific HR guidance built into your tools.
          </h2>
          <p className="text-sm mb-6" style={{ color: MUTED }}>
            Matcha tracks compliance changes across all 50 states and surfaces
            them where you need them — at the point of hiring, terminating,
            and writing policies.
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

      {!embedded && <MarketingFooter />}
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}
