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

function mkT(embedded?: boolean) {
  return embedded ? {
    ink: '#e4e4e7', bg: 'transparent', muted: '#71717a',
    line: '#3f3f46', display: 'inherit',
    cardBg: '#18181b',
    btnPrimary: { backgroundColor: '#15803d', color: '#fff' } as React.CSSProperties,
    btnSecondary: { border: '1px solid #3f3f46', color: '#e4e4e7' } as React.CSSProperties,
  } : {
    ink: INK, bg: BG, muted: MUTED,
    line: LINE, display: DISPLAY,
    cardBg: 'rgba(15,15,15,0.03)',
    btnPrimary: { backgroundColor: INK, color: BG } as React.CSSProperties,
    btnSecondary: { border: `1px solid ${LINE}`, color: INK } as React.CSSProperties,
  }
}

export default function GlossaryTerm({ embedded }: { embedded?: boolean }) {
  const { slug } = useParams<{ slug: string }>()
  const [showPricing, setShowPricing] = useState(false)
  const root = embedded ? '/app/resources' : '/resources'
  const t = mkT(embedded)

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
      <div style={embedded ? { color: t.ink } : { backgroundColor: t.bg, color: t.ink, minHeight: '100vh' }}>
        {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}
        <main className={embedded ? 'text-center' : 'pt-28 pb-20 max-w-[700px] mx-auto px-6 sm:px-10 text-center'}>
          <h1 className="text-3xl mb-4" style={{ fontFamily: t.display, color: t.ink }}>
            Term not found
          </h1>
          <p className="mb-6" style={{ color: t.muted }}>
            We don't have a definition for "{slug}" yet.
          </p>
          <Link
            to={`${root}/glossary`}
            className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
            style={t.btnPrimary}
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
    <div style={embedded ? { color: t.ink } : { backgroundColor: t.bg, color: t.ink, minHeight: '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={embedded ? '' : 'pt-28 pb-20 max-w-[760px] mx-auto px-6 sm:px-10'}>
        <nav className={`flex items-center gap-2 text-xs mb-8 flex-wrap ${embedded ? 'text-vsc-text/40' : ''}`} style={embedded ? undefined : { color: t.muted }}>
          <Link to={root} className={embedded ? 'hover:text-vsc-text/70 transition-colors' : 'hover:opacity-60'}>Resources</Link>
          <ChevronRight className={`w-3 h-3 ${embedded ? 'text-vsc-text/20' : ''}`} />
          <Link to={`${root}/glossary`} className={embedded ? 'hover:text-vsc-text/70 transition-colors' : 'hover:opacity-60'}>Glossary</Link>
          <ChevronRight className={`w-3 h-3 ${embedded ? 'text-vsc-text/20' : ''}`} />
          <span className={embedded ? 'text-vsc-text/60' : ''} style={embedded ? undefined : { color: t.ink }}>{term.abbreviation ?? term.term}</span>
        </nav>

        <header className="mb-10">
          <span
            className={`inline-block text-[10px] tracking-wider px-2 py-1 rounded mb-4 ${embedded ? 'border border-vsc-border text-vsc-text/40' : ''}`}
            style={embedded ? undefined : { border: `1px solid ${t.line}`, color: t.muted }}
          >
            {CATEGORIES_LABEL[term.category].toUpperCase()}
          </span>
          <h1
            className={embedded ? "text-2xl font-semibold text-vsc-text mb-2" : "text-4xl sm:text-5xl tracking-tight mb-3"}
            style={embedded ? undefined : { fontFamily: t.display, fontWeight: 500, color: t.ink }}
          >
            {term.abbreviation ?? term.term}
          </h1>
          {term.abbreviation && (
            <p className={`text-xl mb-2 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted, fontFamily: t.display }}>
              {term.term}
            </p>
          )}
          <p className={`text-lg mt-4 ${embedded ? 'text-vsc-text/80' : ''}`} style={embedded ? undefined : { color: t.ink, opacity: 0.8 }}>
            {term.short}
          </p>
        </header>

        <article
          className={`text-base leading-relaxed mb-12 ${embedded ? 'text-vsc-text/80' : ''}`}
          style={embedded ? undefined : { color: t.ink, opacity: 0.85 }}
        >
          {term.definition.split('\n').map((para, i) => (
            <p key={i} className="mb-4">{para}</p>
          ))}
        </article>

        {related.length > 0 && (
          <section className="mb-12">
            <h2
              className={`text-sm tracking-wider mb-4 uppercase ${embedded ? 'text-vsc-text/40' : ''}`}
              style={embedded ? undefined : { color: t.muted }}
            >
              Related Terms
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {related.map(r => (
                <Link
                  key={r.slug}
                  to={`${root}/glossary/${r.slug}`}
                  className={embedded
                    ? 'border border-vsc-border bg-vsc-panel rounded-xl p-4 block hover:border-vsc-text/30 transition-colors'
                    : 'p-4 rounded-xl block transition-opacity hover:opacity-80'}
                  style={embedded ? undefined : { border: `1px solid ${t.line}` }}
                >
                  <div
                    className={`text-base mb-1 ${embedded ? 'font-semibold text-vsc-text' : ''}`}
                    style={embedded ? undefined : { fontFamily: t.display, color: t.ink, fontWeight: 500 }}
                  >
                    {r.abbreviation ?? r.term}
                  </div>
                  <div className={`text-xs ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>
                    {r.short}
                  </div>
                </Link>
              ))}
            </div>
          </section>
        )}

        <section
          className={embedded ? 'rounded-xl border border-vsc-border bg-vsc-panel p-6' : 'p-8 rounded-2xl'}
          style={embedded ? undefined : { border: `1px solid ${t.line}`, backgroundColor: t.cardBg }}
        >
          <h2 className={embedded ? 'text-base font-semibold text-vsc-text mb-2' : 'text-xl mb-3'} style={embedded ? undefined : { fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
            Stop guessing. Get state-specific HR guidance built into your tools.
          </h2>
          <p className={embedded ? 'text-sm text-vsc-text/50 mb-4' : 'text-sm mb-6'} style={embedded ? undefined : { color: t.muted }}>
            Matcha tracks compliance changes across all 50 states and surfaces
            them where you need them — at the point of hiring, terminating,
            and writing policies.
          </p>
          <button
            onClick={() => setShowPricing(true)}
            className={embedded
              ? 'inline-flex items-center h-9 px-4 rounded-lg text-xs font-medium bg-zinc-700 hover:bg-zinc-600 text-white transition-colors'
              : 'inline-flex items-center px-5 h-10 rounded-full text-sm font-medium'}
            style={embedded ? undefined : t.btnPrimary}
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
