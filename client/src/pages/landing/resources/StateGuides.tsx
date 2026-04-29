import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, MapPin, Search } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import { PricingContactModal } from '../../../components/PricingContactModal'
import { api } from '../../../api/client'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type StateEntry = {
  slug: string
  code: string
  name: string
  requirement_count: number
  last_verified: string | null
}

type StateList = { states: StateEntry[] }

export default function StateGuides() {
  const [states, setStates] = useState<StateEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [showPricing, setShowPricing] = useState(false)
  const [query, setQuery] = useState('')

  useEffect(() => {
    document.title = 'State HR Compliance Guides — Matcha'
    api.get<StateList>('/resources/state-guides')
      .then(d => setStates(d.states))
      .catch(() => setStates([]))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return states
    return states.filter(s => s.name.toLowerCase().includes(q) || s.code.toLowerCase() === q)
  }, [states, query])

  return (
    <div style={{ backgroundColor: BG, color: INK, minHeight: '100vh' }}>
      <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />

      <main className="pt-28 pb-20 max-w-[1100px] mx-auto px-6 sm:px-10">
        <nav className="flex items-center gap-2 text-xs mb-8" style={{ color: MUTED }}>
          <Link to="/resources" className="hover:opacity-60">Resources</Link>
          <ChevronRight className="w-3 h-3" />
          <span style={{ color: INK }}>State Compliance Guides</span>
        </nav>

        <header className="mb-10 max-w-2xl">
          <h1
            className="text-5xl sm:text-6xl tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            State Compliance Guides
          </h1>
          <p className="mt-4 text-base" style={{ color: MUTED }}>
            Wage rules, paid leave, final-paycheck timing, and the rest of
            what changes the moment you cross a state line. Sourced from
            official statutes and tracked for changes.
          </p>
        </header>

        <div className="mb-8">
          <div
            className="flex items-center gap-3 px-4 h-12 rounded-full max-w-md"
            style={{ border: `1px solid ${LINE}` }}
          >
            <Search className="w-4 h-4" style={{ color: MUTED }} />
            <input
              type="text"
              placeholder="Search states (California, NY, Texas…)"
              value={query}
              onChange={e => setQuery(e.target.value)}
              className="flex-1 bg-transparent outline-none text-sm"
              style={{ color: INK }}
            />
          </div>
        </div>

        {loading ? (
          <p style={{ color: MUTED }}>Loading states…</p>
        ) : filtered.length === 0 ? (
          <p style={{ color: MUTED }}>No states match "{query}".</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {filtered.map(st => (
              <Link
                key={st.slug}
                to={`/resources/states/${st.slug}`}
                className="block p-5 rounded-xl transition-opacity hover:opacity-80"
                style={{ border: `1px solid ${LINE}` }}
              >
                <div className="flex items-start justify-between mb-3">
                  <MapPin className="w-4 h-4" style={{ color: MUTED }} />
                  <span
                    className="text-[10px] tracking-wider px-2 py-0.5 rounded"
                    style={{ border: `1px solid ${LINE}`, color: MUTED }}
                  >
                    {st.code}
                  </span>
                </div>
                <h3
                  className="text-xl mb-1"
                  style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
                >
                  {st.name}
                </h3>
                <p className="text-xs" style={{ color: MUTED }}>
                  {st.requirement_count} requirements tracked
                </p>
              </Link>
            ))}
          </div>
        )}

        <section
          className="mt-16 p-8 rounded-2xl"
          style={{ border: `1px solid ${LINE}`, backgroundColor: 'rgba(15,15,15,0.03)' }}
        >
          <h2 className="text-2xl mb-3" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
            Don't see your state?
          </h2>
          <p className="text-sm mb-6 max-w-2xl" style={{ color: MUTED }}>
            We're expanding state coverage continuously. Matcha customers get
            access to county and city-level data too — Berkeley, NYC, Chicago,
            and 70+ municipalities are already in the database.
          </p>
          <button
            onClick={() => setShowPricing(true)}
            className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
            style={{ backgroundColor: INK, color: BG }}
          >
            Get full coverage →
          </button>
        </section>
      </main>

      <MarketingFooter />
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}
