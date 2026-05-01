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

export default function Glossary({ embedded }: { embedded?: boolean }) {
  const [showPricing, setShowPricing] = useState(false)
  const [query, setQuery] = useState('')
  const root = embedded ? '/app/resources' : '/resources'

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
    for (const t of filtered) {
      const k = firstLetter(t)
      ;(m[k] ??= []).push(t)
    }
    return m
  }, [filtered])

  const presentLetters = ALPHA.filter(l => grouped[l]?.length)

  return (
    <div style={{ backgroundColor: BG, color: INK, minHeight: embedded ? undefined : '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={`${embedded ? 'pt-6' : 'pt-28'} pb-20 max-w-[1100px] mx-auto px-6 sm:px-10`}>
        <nav className="flex items-center gap-2 text-xs mb-8" style={{ color: MUTED }}>
          <Link to={root} className="hover:opacity-60">Resources</Link>
          <ChevronRight className="w-3 h-3" />
          <span style={{ color: INK }}>Glossary</span>
        </nav>

        <header className="mb-10 max-w-2xl">
          <h1
            className="text-5xl sm:text-6xl tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            HR Glossary
          </h1>
          <p className="mt-4 text-base" style={{ color: MUTED }}>
            Plain-English definitions for the alphabet soup of employment law,
            agencies, and HR concepts. {GLOSSARY.length}+ terms and growing.
          </p>
        </header>

        <div className="mb-10">
          <div
            className="flex items-center gap-3 px-4 h-12 rounded-full max-w-md"
            style={{ border: `1px solid ${LINE}` }}
          >
            <Search className="w-4 h-4" style={{ color: MUTED }} />
            <input
              type="text"
              placeholder="Search terms (FLSA, COBRA, retaliation…)"
              value={query}
              onChange={e => setQuery(e.target.value)}
              className="flex-1 bg-transparent outline-none text-sm"
              style={{ color: INK }}
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
                style={{ color: INK, border: `1px solid ${LINE}` }}
              >
                {letter}
              </a>
            ) : (
              <span
                key={letter}
                className="w-8 h-8 inline-flex items-center justify-center text-sm rounded"
                style={{ color: 'rgba(0,0,0,0.2)' }}
              >
                {letter}
              </span>
            )
          })}
        </div>

        {presentLetters.length === 0 ? (
          <p style={{ color: MUTED }}>No terms match "{query}".</p>
        ) : (
          presentLetters.map(letter => (
            <section key={letter} id={`letter-${letter}`} className="mb-12 scroll-mt-28">
              <h2
                className="text-3xl mb-6"
                style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
              >
                {letter}
              </h2>
              <div className="flex flex-col gap-3">
                {grouped[letter].map(t => (
                  <Link
                    key={t.slug}
                    to={`${root}/glossary/${t.slug}`}
                    className="block p-5 rounded-xl transition-opacity hover:opacity-80"
                    style={{ border: `1px solid ${LINE}` }}
                  >
                    <div className="flex items-baseline gap-3 mb-1 flex-wrap">
                      <h3
                        className="text-lg"
                        style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
                      >
                        {t.abbreviation ?? t.term}
                      </h3>
                      {t.abbreviation && (
                        <span className="text-sm" style={{ color: MUTED }}>
                          {t.term}
                        </span>
                      )}
                      <span
                        className="text-[10px] tracking-wider px-2 py-1 rounded ml-auto"
                        style={{ border: `1px solid ${LINE}`, color: MUTED }}
                      >
                        {CATEGORIES_LABEL[t.category]}
                      </span>
                    </div>
                    <p className="text-sm" style={{ color: MUTED }}>
                      {t.short}
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
