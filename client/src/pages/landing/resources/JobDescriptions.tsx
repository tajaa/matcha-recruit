import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, Download, FileText, Search } from 'lucide-react'

import MarketingNav from '../MarketingNav'
import MarketingFooter from '../MarketingFooter'
import { PricingContactModal } from '../../../components/PricingContactModal'
import { useMe } from '../../../hooks/useMe'
import { INDUSTRIES, JOB_DESCRIPTIONS, type Industry, type JobDescription } from './jobDescriptionsData'

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
    chipActiveBg: '#27272a', chipActiveColor: '#e4e4e7', chipActiveBorder: '#3f3f46',
    btnPrimary: { backgroundColor: '#15803d', color: '#fff' } as React.CSSProperties,
  } : {
    ink: INK, bg: BG, muted: MUTED,
    line: LINE, display: DISPLAY,
    cardBg: 'rgba(15,15,15,0.03)',
    chipActiveBg: INK, chipActiveColor: BG, chipActiveBorder: INK,
    btnPrimary: { backgroundColor: INK, color: BG } as React.CSSProperties,
  }
}

export default function JobDescriptions({ embedded }: { embedded?: boolean }) {
  const [showPricing, setShowPricing] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Industry | 'all'>('all')
  const root = embedded ? '/app/resources' : '/resources'
  const t = mkT(embedded)
  const { me } = useMe()
  const isLoggedIn = !!me?.user

  function handleDownload(jd: JobDescription) {
    if (!jd.downloadUrl) return
    if (!isLoggedIn) {
      const next = encodeURIComponent(`${root}/templates/job-descriptions/${jd.slug}`)
      window.location.href = `/auth/resources-signup?next=${next}`
      return
    }
    window.open(jd.downloadUrl, '_blank', 'noopener,noreferrer')
  }

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
    <div style={embedded ? { color: t.ink } : { backgroundColor: t.bg, color: t.ink, minHeight: '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={embedded ? '' : 'pt-28 pb-20 max-w-[1100px] mx-auto px-6 sm:px-10'}>
        {!embedded && (
          <nav className="flex items-center gap-2 text-xs mb-8 flex-wrap" style={{ color: t.muted }}>
            <Link to={root} className="hover:opacity-60">Resources</Link>
            <ChevronRight className="w-3 h-3" />
            <Link to={`${root}/templates`} className="hover:opacity-60">Templates</Link>
            <ChevronRight className="w-3 h-3" />
            <span style={{ color: t.ink }}>Job Descriptions Library</span>
          </nav>
        )}

        {embedded ? (
          <div className="mb-5">
            <h1 className="text-2xl font-semibold text-vsc-text">Job Descriptions</h1>
            <p className="mt-1 text-sm text-vsc-text/50">
              {JOB_DESCRIPTIONS.length} ready-to-edit job descriptions across {INDUSTRIES.length} industries.
            </p>
          </div>
        ) : (
          <header className="mb-10 max-w-2xl">
            <h1
              className="text-5xl sm:text-6xl tracking-tight"
              style={{ fontFamily: t.display, fontWeight: 500, color: t.ink }}
            >
              Job Descriptions Library
            </h1>
            <p className="mt-4 text-base" style={{ color: t.muted }}>
              {JOB_DESCRIPTIONS.length} ready-to-edit job descriptions across
              {' '}{INDUSTRIES.length} industries. Pick the role you need —
              no bulk download, no fluff.
            </p>
          </header>
        )}

        <div className={embedded ? 'mb-3' : 'mb-6'}>
          <div
            className={embedded
              ? 'flex items-center gap-2 px-3 h-9 rounded-md max-w-md border border-vsc-border bg-vsc-bg'
              : 'flex items-center gap-3 px-4 h-12 rounded-full max-w-md'}
            style={embedded ? undefined : { border: `1px solid ${t.line}` }}
          >
            <Search className={embedded ? 'w-3.5 h-3.5 text-vsc-text/40' : 'w-4 h-4'} style={embedded ? undefined : { color: t.muted }} />
            <input
              type="text"
              placeholder="Search roles…"
              value={query}
              onChange={e => setQuery(e.target.value)}
              className={embedded
                ? 'flex-1 bg-transparent outline-none text-xs text-vsc-text placeholder:text-vsc-text/40'
                : 'flex-1 bg-transparent outline-none text-sm'}
              style={embedded ? undefined : { color: t.ink }}
            />
          </div>
        </div>

        <div className={embedded ? 'flex flex-wrap gap-1.5 mb-5' : 'flex flex-wrap gap-2 mb-10'}>
          <FilterChip t={t} embedded={embedded}active={filter === 'all'} onClick={() => setFilter('all')}>
            All ({JOB_DESCRIPTIONS.length})
          </FilterChip>
          {INDUSTRIES.map(ind => {
            const count = JOB_DESCRIPTIONS.filter(j => j.industry === ind).length
            return (
              <FilterChip t={t} embedded={embedded}key={ind} active={filter === ind} onClick={() => setFilter(ind)}>
                {ind} ({count})
              </FilterChip>
            )
          })}
        </div>

        {grouped.size === 0 ? (
          <p style={{ color: t.muted }}>No roles match "{query}".</p>
        ) : (
          <div className={embedded ? 'flex flex-col gap-6' : 'flex flex-col gap-10'}>
            {Array.from(grouped.entries()).map(([industry, jobs]) => (
              <section key={industry}>
                {embedded ? (
                  <h2 className="text-xs uppercase tracking-wider font-medium text-vsc-text/50 mb-3 pb-2 border-b border-vsc-border">
                    {industry} <span className="text-vsc-text/30 normal-case font-normal">({jobs.length})</span>
                  </h2>
                ) : (
                  <h2
                    className="text-2xl mb-4 pb-2"
                    style={{
                      fontFamily: t.display, color: t.ink, fontWeight: 500,
                      borderBottom: `1px solid ${t.line}`,
                    }}
                  >
                    {industry} <span style={{ color: t.muted, fontSize: '0.875rem', fontWeight: 400 }}>({jobs.length})</span>
                  </h2>
                )}
                <div className={embedded ? 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2' : 'grid grid-cols-1 sm:grid-cols-2 gap-3'}>
                  {jobs.map(j => (
                    embedded ? (
                      <article key={j.slug} className="p-3 rounded-md border border-vsc-border bg-vsc-panel hover:border-vsc-text/30 flex flex-col transition-colors">
                        <div className="flex items-start gap-2 mb-1.5">
                          <FileText className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-vsc-text/50" />
                          <Link
                            to={`${root}/templates/job-descriptions/${j.slug}`}
                            className="text-sm font-medium text-vsc-text flex-1 hover:text-white"
                          >
                            {j.title}
                          </Link>
                        </div>
                        <p className="text-[11px] mb-3 ml-5 text-vsc-text/50 line-clamp-2">{j.description}</p>
                        <div className="ml-5 flex items-center gap-1.5">
                          <Link
                            to={`${root}/templates/job-descriptions/${j.slug}`}
                            className="text-[11px] px-2 h-6 rounded-md inline-flex items-center border border-vsc-border text-vsc-text/70 hover:text-vsc-text hover:border-vsc-text/40 transition-colors"
                          >
                            View
                          </Link>
                          {j.downloadUrl && (
                            <button
                              onClick={() => handleDownload(j)}
                              className="inline-flex items-center gap-1 text-[11px] px-2 h-6 rounded-md bg-zinc-700 hover:bg-zinc-600 text-white font-medium transition-colors"
                            >
                              <Download className="w-3 h-3" />
                              DOCX
                            </button>
                          )}
                        </div>
                      </article>
                    ) : (
                      <article
                        key={j.slug}
                        className="p-4 rounded-xl flex flex-col"
                        style={{ border: `1px solid ${t.line}` }}
                      >
                        <div className="flex items-start gap-3 mb-2">
                          <FileText className="w-4 h-4 mt-1 flex-shrink-0" style={{ color: t.ink }} />
                          <Link
                            to={`${root}/templates/job-descriptions/${j.slug}`}
                            className="text-base flex-1 hover:opacity-70"
                            style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}
                          >
                            {j.title}
                          </Link>
                        </div>
                        <p className="text-xs mb-4 ml-7" style={{ color: t.muted }}>
                          {j.description}
                        </p>
                        <div className="ml-7 flex items-center gap-2">
                          <Link
                            to={`${root}/templates/job-descriptions/${j.slug}`}
                            className="text-xs px-3 h-7 rounded-full inline-flex items-center hover:opacity-80"
                            style={{ border: `1px solid ${t.line}`, color: t.muted }}
                          >
                            View
                          </Link>
                          {j.downloadUrl && (
                            <button
                              onClick={() => handleDownload(j)}
                              className="inline-flex items-center gap-1 text-xs px-3 h-7 rounded-full hover:opacity-80"
                              style={t.btnPrimary}
                            >
                              <Download className="w-3 h-3" />
                              DOCX
                            </button>
                          )}
                        </div>
                      </article>
                    )
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}

        {embedded ? (
          <section className="mt-8 p-5 rounded-xl border border-vsc-border bg-vsc-panel">
            <h2 className="text-base font-semibold text-vsc-text mb-1">
              Custom job descriptions for your business
            </h2>
            <p className="text-xs text-vsc-text/50 mb-4 max-w-2xl">
              Matcha generates JDs tailored to your business — specific responsibilities,
              comp range, BFOQ-safe requirements, and DEI-reviewed language.
            </p>
            <button
              onClick={() => setShowPricing(true)}
              className="inline-flex items-center justify-center px-4 h-8 rounded-md text-xs font-medium bg-zinc-700 hover:bg-zinc-600 text-white transition-colors"
            >
              Talk to sales →
            </button>
          </section>
        ) : (
        <section
          className="mt-20 p-8 rounded-2xl"
          style={{ border: `1px solid ${t.line}`, backgroundColor: t.cardBg }}
        >
          <h2 className="text-2xl mb-3" style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
            Download all {JOB_DESCRIPTIONS.length} job descriptions
          </h2>
          <p className="text-sm mb-6 max-w-2xl" style={{ color: t.muted }}>
            Free account unlocks DOCX downloads for every role in the library —
            editable, compliant, and ready to post.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link
              to="/signup"
              className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
              style={t.btnPrimary}
            >
              Create free account →
            </Link>
            <button
              onClick={() => setShowPricing(true)}
              className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
              style={{ border: `1px solid ${t.line}`, color: t.ink }}
            >
              Talk to sales
            </button>
          </div>
        </section>
        )}
      </main>

      {!embedded && <MarketingFooter />}
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}

function FilterChip({ t, active, onClick, children, embedded }: { t: ReturnType<typeof mkT>; active: boolean; onClick: () => void; children: React.ReactNode; embedded?: boolean }) {
  if (embedded) {
    return (
      <button
        onClick={onClick}
        className={`text-[11px] px-2.5 h-6 rounded-md transition-colors ${
          active
            ? 'bg-vsc-panel text-vsc-text border border-vsc-border'
            : 'bg-transparent text-vsc-text/50 hover:text-vsc-text border border-vsc-border hover:border-vsc-text/40'
        }`}
      >
        {children}
      </button>
    )
  }
  return (
    <button
      onClick={onClick}
      className="text-xs px-3 h-8 rounded-full transition-opacity hover:opacity-80"
      style={{
        backgroundColor: active ? t.chipActiveBg : 'transparent',
        color: active ? t.chipActiveColor : t.ink,
        border: `1px solid ${active ? t.chipActiveBorder : t.line}`,
      }}
    >
      {children}
    </button>
  )
}
