import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, FileText, Search } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import { PricingContactModal } from '../../../components/PricingContactModal'
import { INDUSTRIES, JOB_DESCRIPTIONS, type Industry, type JobDescription } from './jobDescriptionsData'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

export default function JobDescriptions({ embedded }: { embedded?: boolean }) {
  const [showPricing, setShowPricing] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Industry | 'all'>('all')
  const root = embedded ? '/app/resources' : '/resources'

  useEffect(() => {
    document.title = 'Job Descriptions Library — Matcha'
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return JOB_DESCRIPTIONS.filter(j => {
      if (filter !== 'all' && j.industry !== filter) return false
      if (q && !j.title.toLowerCase().includes(q) && !j.description.toLowerCase().includes(q)) return false
      return true
    })
  }, [query, filter])

  const grouped = useMemo(() => {
    const m = new Map<Industry, JobDescription[]>()
    for (const j of filtered) {
      const arr = m.get(j.industry) ?? []
      arr.push(j)
      m.set(j.industry, arr)
    }
    return m
  }, [filtered])

  return (
    <div style={{ backgroundColor: BG, color: INK, minHeight: embedded ? undefined : '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={`${embedded ? 'pt-6' : 'pt-28'} pb-20 max-w-[1100px] mx-auto px-6 sm:px-10`}>
        <nav className="flex items-center gap-2 text-xs mb-8 flex-wrap" style={{ color: MUTED }}>
          <Link to={root} className="hover:opacity-60">Resources</Link>
          <ChevronRight className="w-3 h-3" />
          <Link to={`${root}/templates`} className="hover:opacity-60">Templates</Link>
          <ChevronRight className="w-3 h-3" />
          <span style={{ color: INK }}>Job Descriptions Library</span>
        </nav>

        <header className="mb-10 max-w-2xl">
          <h1
            className="text-5xl sm:text-6xl tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
          >
            Job Descriptions Library
          </h1>
          <p className="mt-4 text-base" style={{ color: MUTED }}>
            {JOB_DESCRIPTIONS.length} ready-to-edit job descriptions across
            {' '}{INDUSTRIES.length} industries. Pick the role you need —
            no bulk download, no fluff.
          </p>
        </header>

        <div className="mb-6">
          <div
            className="flex items-center gap-3 px-4 h-12 rounded-full max-w-md"
            style={{ border: `1px solid ${LINE}` }}
          >
            <Search className="w-4 h-4" style={{ color: MUTED }} />
            <input
              type="text"
              placeholder="Search roles (nurse, line cook, recruiter…)"
              value={query}
              onChange={e => setQuery(e.target.value)}
              className="flex-1 bg-transparent outline-none text-sm"
              style={{ color: INK }}
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mb-10">
          <FilterChip active={filter === 'all'} onClick={() => setFilter('all')}>
            All ({JOB_DESCRIPTIONS.length})
          </FilterChip>
          {INDUSTRIES.map(ind => {
            const count = JOB_DESCRIPTIONS.filter(j => j.industry === ind).length
            return (
              <FilterChip key={ind} active={filter === ind} onClick={() => setFilter(ind)}>
                {ind} ({count})
              </FilterChip>
            )
          })}
        </div>

        {grouped.size === 0 ? (
          <p style={{ color: MUTED }}>No roles match "{query}".</p>
        ) : (
          <div className="flex flex-col gap-10">
            {Array.from(grouped.entries()).map(([industry, jobs]) => (
              <section key={industry}>
                <h2
                  className="text-2xl mb-4 pb-2"
                  style={{
                    fontFamily: DISPLAY, color: INK, fontWeight: 500,
                    borderBottom: `1px solid ${LINE}`,
                  }}
                >
                  {industry} <span style={{ color: MUTED, fontSize: '0.875rem', fontWeight: 400 }}>({jobs.length})</span>
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {jobs.map(j => (
                    <article
                      key={j.slug}
                      className="p-4 rounded-xl flex flex-col"
                      style={{ border: `1px solid ${LINE}` }}
                    >
                      <div className="flex items-start gap-3 mb-2">
                        <FileText className="w-4 h-4 mt-1 flex-shrink-0" style={{ color: INK }} />
                        <h3
                          className="text-base flex-1"
                          style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
                        >
                          {j.title}
                        </h3>
                      </div>
                      <p className="text-xs mb-4 ml-7" style={{ color: MUTED }}>
                        {j.description}
                      </p>
                      <div className="ml-7 flex items-center justify-between gap-2">
                        <span
                          className="text-[10px] tracking-wider px-2 py-1 rounded"
                          style={{ border: `1px solid ${LINE}`, color: MUTED }}
                        >
                          COMING SOON
                        </span>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}

        <section
          className="mt-20 p-8 rounded-2xl"
          style={{ border: `1px solid ${LINE}`, backgroundColor: 'rgba(15,15,15,0.03)' }}
        >
          <h2 className="text-2xl mb-3" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
            Need a custom job description?
          </h2>
          <p className="text-sm mb-6 max-w-2xl" style={{ color: MUTED }}>
            Matcha generates job descriptions tailored to your business —
            specific responsibilities, comp range, BFOQ-safe requirements,
            and DEI-reviewed language.
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

function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="text-xs px-3 h-8 rounded-full transition-opacity hover:opacity-80"
      style={{
        backgroundColor: active ? INK : 'transparent',
        color: active ? BG : INK,
        border: `1px solid ${active ? INK : LINE}`,
      }}
    >
      {children}
    </button>
  )
}
