import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Search } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import { PricingContactModal } from '../../../components/PricingContactModal'
import { GLOSSARY, CATEGORIES_LABEL, type GlossaryTerm } from './glossaryData'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

const ALPHA = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')

function firstLetter(t: GlossaryTerm): string {
  const c = (t.abbreviation ?? t.term)[0].toUpperCase()
  return /[A-Z]/.test(c) ? c : '#'
}

function mkT(embedded?: boolean) {
  return embedded ? {
    ink: '#e4e4e7', bg: 'transparent', muted: '#71717a',
    line: '#3f3f46', display: 'inherit',
    btnPrimary: { backgroundColor: '#15803d', color: '#fff' } as React.CSSProperties,
  } : {
    ink: INK, bg: BG, muted: MUTED,
    line: LINE, display: DISPLAY,
    btnPrimary: { backgroundColor: INK, color: BG } as React.CSSProperties,
  }
}

export default function Glossary({ embedded }: { embedded?: boolean }) {
  const [showPricing, setShowPricing] = useState(false)
  const [query, setQuery] = useState('')
  const root = embedded ? '/app/resources' : '/resources'
  const t = mkT(embedded)

  useEffect(() => {
    document.title = 'HR Glossary — Matcha'
  }, [])

  const sorted = useMemo(
    () => [...GLOSSARY].sort((a, b) => (a.abbreviation ?? a.term).localeCompare(b.abbreviation ?? b.term)),
    [],
  )

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return sorted
    return sorted.filter(
      t =>
        t.term.toLowerCase().includes(q) ||
        t.abbreviation?.toLowerCase().includes(q) ||
        t.short.toLowerCase().includes(q) ||
        t.slug.includes(q),
    )
  }, [sorted, query])

  const grouped = useMemo(() => {
    const m: Record<string, GlossaryTerm[]> = {}
    for (const term of filtered) {
      const k = firstLetter(term)
      ;(m[k] ??= []).push(term)
    }
    return m
  }, [filtered])

  const presentLetters = ALPHA.filter(l => grouped[l]?.length)

  return (
    <div style={embedded ? { color: t.ink } : { backgroundColor: t.bg, color: t.ink, minHeight: '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={embedded ? '' : 'pt-28 pb-20 max-w-[1100px] mx-auto px-6 sm:px-10'}>
        <nav className="flex items-center gap-2 text-xs mb-8" style={{ color: t.muted }}>
          <Link to={root} className="hover:opacity-60">Resources</Link>
          <ChevronRight className="w-3 h-3" />
          <span style={{ color: t.ink }}>Glossary</span>
        </nav>

        <header className="mb-10 max-w-2xl">
          <h1
            className={embedded ? "text-2xl font-semibold" : "text-5xl sm:text-6xl tracking-tight"}
            style={embedded ? { color: t.ink } : { fontFamily: t.display, fontWeight: 500, color: t.ink }}
          >
            HR Glossary
          </h1>
          <p className="mt-4 text-base" style={{ color: t.muted }}>
            Plain-English definitions for the alphabet soup of employment law,
            agencies, and HR concepts. {GLOSSARY.length}+ terms and growing.
          </p>
        </header>

        <div className="mb-10">
          <div
            className="flex items-center gap-3 px-4 h-12 rounded-full max-w-md"
            style={{ border: `1px solid ${t.line}` }}
          >
            <Search className="w-4 h-4" style={{ color: t.muted }} />
            <input
              type="text"
              placeholder="Search terms (FLSA, COBRA, retaliation…)"
              value={query}
              onChange={e => setQuery(e.target.value)}
              className="flex-1 bg-transparent outline-none text-sm"
              style={{ color: t.ink }}
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mb-10">
          {ALPHA.map(letter => {
            const has = !!grouped[letter]?.length
            return has ? (
              <a
                key={letter}
                href={`#letter-${letter}`}
                className="w-8 h-8 inline-flex items-center justify-center text-sm rounded transition-opacity hover:opacity-60"
                style={{ color: t.ink, border: `1px solid ${t.line}` }}
              >
                {letter}
              </a>
            ) : (
              <span
                key={letter}
                className="w-8 h-8 inline-flex items-center justify-center text-sm rounded"
                style={{ color: embedded ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.2)' }}
              >
                {letter}
              </span>
            )
          })}
        </div>

        {presentLetters.length === 0 ? (
          <p style={{ color: t.muted }}>No terms match "{query}".</p>
        ) : (
          presentLetters.map(letter => (
            <section key={letter} id={`letter-${letter}`} className="mb-12 scroll-mt-28">
              <h2
                className="text-3xl mb-6"
                style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}
              >
                {letter}
              </h2>
              <div className="flex flex-col gap-3">
                {grouped[letter].map(term => (
                  <Link
                    key={term.slug}
                    to={`${root}/glossary/${term.slug}`}
                    className="block p-5 rounded-xl transition-opacity hover:opacity-80"
                    style={{ border: `1px solid ${t.line}` }}
                  >
                    <div className="flex items-baseline gap-3 mb-1 flex-wrap">
                      <h3
                        className="text-lg"
                        style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}
                      >
                        {term.abbreviation ?? term.term}
                      </h3>
                      {term.abbreviation && (
                        <span className="text-sm" style={{ color: t.muted }}>
                          {term.term}
                        </span>
                      )}
                      <span
                        className="text-[10px] tracking-wider px-2 py-1 rounded ml-auto"
                        style={{ border: `1px solid ${t.line}`, color: t.muted }}
                      >
                        {CATEGORIES_LABEL[term.category]}
                      </span>
                    </div>
                    <p className="text-sm" style={{ color: t.muted }}>
                      {term.short}
                    </p>
                  </Link>
                ))}
              </div>
            </section>
          ))
        )}
      </main>

      {!embedded && <MarketingFooter />}
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}
