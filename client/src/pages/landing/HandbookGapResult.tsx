import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import {
  AlertOctagon, AlertTriangle, CheckCircle2, Info, Loader2, ShieldCheck,
} from 'lucide-react'

import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { useMe } from '../../hooks/useMe'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

const BASE = import.meta.env.VITE_API_URL ?? '/api'
const POLL_INTERVAL_MS = 2500

type Severity = 'critical' | 'important' | 'recommended'

interface Gap {
  state: string
  requirement_key: string
  requirement_title: string
  covered: boolean
  severity: Severity
  citation?: string | null
  what_good_looks_like?: string
  matched_section_title?: string | null
}

interface ReportPayload {
  report_id: string
  status: 'processing' | 'ready' | 'failed'
  states: string[]
  industry: string | null
  gap_counts: {
    critical: number
    important: number
    recommended: number
    total_gaps: number
    total_states: number
    by_state: Record<string, { critical?: number; important?: number; recommended?: number; covered?: number }>
  }
  sample_gaps: Gap[]
  gaps?: Gap[]
  is_owner: boolean
  error?: string
  created_at?: string | null
  completed_at?: string | null
}

export default function HandbookGapResult() {
  const { reportId } = useParams<{ reportId: string }>()
  const { me, loading: meLoading } = useMe()
  const [report, setReport] = useState<ReportPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const cancelledRef = useRef(false)

  useEffect(() => {
    cancelledRef.current = false
    if (!reportId || !me) return

    async function fetchOnce() {
      const token = localStorage.getItem('matcha_access_token')
      const res = await fetch(`${BASE}/resources/handbook-gap-analyzer/report/${reportId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || 'Could not load the report')
      }
      return res.json() as Promise<ReportPayload>
    }

    let timer: ReturnType<typeof setTimeout> | null = null
    async function tick() {
      try {
        const data = await fetchOnce()
        if (cancelledRef.current) return
        setReport(data)
        if (data.status === 'processing') {
          timer = setTimeout(tick, POLL_INTERVAL_MS)
        }
      } catch (e) {
        if (!cancelledRef.current) {
          setError(e instanceof Error ? e.message : 'Could not load the report')
        }
      }
    }
    tick()
    return () => {
      cancelledRef.current = true
      if (timer) clearTimeout(timer)
    }
  }, [reportId, me])

  if (!meLoading && !me) {
    const next = encodeURIComponent(`/handbook-gap-analyzer/result/${reportId}`)
    return <Navigate to={`/login?next=${next}`} replace />
  }

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen">
      <MarketingNav />

      <main className="max-w-[1100px] mx-auto px-6 sm:px-10 pt-28 pb-24">
        {(meLoading || (!report && !error)) && <Loading />}
        {error && <ErrorBlock message={error} />}
        {report && report.status === 'failed' && (
          <ErrorBlock message={report.error || 'The audit did not complete successfully.'} />
        )}
        {report && report.status === 'processing' && <Processing />}
        {report && report.status === 'ready' && <ResultBody report={report} />}
      </main>

      <MarketingFooter />
    </div>
  )
}

function Loading() {
  return (
    <div className="flex items-center justify-center py-24" style={{ color: MUTED }}>
      <Loader2 className="w-5 h-5 animate-spin mr-2" />
      <span className="text-sm">Loading audit…</span>
    </div>
  )
}

function Processing() {
  return (
    <div className="text-center py-24">
      <Loader2 className="w-8 h-8 animate-spin mx-auto mb-5" style={{ color: INK }} />
      <h1
        className="tracking-tight mb-3"
        style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: '1.75rem', color: INK }}
      >
        Reading your handbook…
      </h1>
      <p className="text-sm max-w-md mx-auto" style={{ color: MUTED }}>
        We're extracting policy sections and grading them against state requirements.
        This usually takes 30–90 seconds.
      </p>
    </div>
  )
}

function ErrorBlock({ message }: { message: string }) {
  return (
    <div
      className="rounded-2xl p-8 text-center"
      style={{ backgroundColor: 'rgba(206,145,120,0.08)', border: '1px solid rgba(206,145,120,0.3)' }}
    >
      <AlertOctagon className="w-7 h-7 mx-auto mb-4" style={{ color: '#8a4a3a' }} />
      <h2 className="text-lg mb-2" style={{ fontFamily: DISPLAY, color: INK }}>Something went wrong.</h2>
      <p className="text-sm" style={{ color: MUTED }}>{message}</p>
      <Link to="/handbook-gap-analyzer" className="inline-block mt-5 underline text-sm" style={{ color: INK }}>
        Try again
      </Link>
    </div>
  )
}

function ResultBody({ report }: { report: ReportPayload }) {
  const { gap_counts, gaps, states } = report

  const groupedGaps = useMemo(() => {
    const all = gaps || []
    const map = new Map<string, Gap[]>()
    for (const g of all) {
      const key = g.state
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(g)
    }
    for (const list of map.values()) {
      list.sort((a, b) => severityRank(a.severity) - severityRank(b.severity))
    }
    return Array.from(map.entries())
  }, [gaps])

  return (
    <>
      <header className="text-center mb-10">
        <p
          className="text-[11px] uppercase tracking-[0.3em] mb-4"
          style={{ color: MUTED, fontFamily: 'var(--font-mono)' }}
        >
          AUDIT COMPLETE
        </p>
        <h1
          className="tracking-tight mb-4"
          style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: 'clamp(2rem, 4vw, 3rem)', color: INK }}
        >
          We found <span style={{ color: gap_counts.total_gaps > 0 ? '#8a4a3a' : '#3f7c5b' }}>
            {gap_counts.total_gaps} gap{gap_counts.total_gaps === 1 ? '' : 's'}
          </span> across {states.length} state{states.length === 1 ? '' : 's'}.
        </h1>
        <p className="text-sm" style={{ color: MUTED }}>
          {states.join(' · ')}
        </p>
      </header>

      <div className="grid grid-cols-3 gap-5 mb-10">
        <SeverityTile
          icon={AlertOctagon}
          label="Critical"
          count={gap_counts.critical}
          accent="#8a4a3a"
          help="Direct termination or liability exposure"
        />
        <SeverityTile
          icon={AlertTriangle}
          label="Important"
          count={gap_counts.important}
          accent="#a47c2c"
          help="State-mandated notice or policy"
        />
        <SeverityTile
          icon={Info}
          label="Recommended"
          count={gap_counts.recommended}
          accent="#5b6f7c"
          help="Best-practice clauses to consider"
        />
      </div>

      <div className="space-y-8">
        {groupedGaps.map(([state, list]) => (
          <section key={state}>
            <div className="flex items-center justify-between mb-4">
              <h2
                className="tracking-tight"
                style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: '1.4rem', color: INK }}
              >
                {state}
              </h2>
              <span className="text-xs" style={{ color: MUTED, fontFamily: 'var(--font-mono)' }}>
                {list.length} gap{list.length === 1 ? '' : 's'}
              </span>
            </div>
            <div className="space-y-3">
              {list.map((g, i) => <GapCard key={`${state}-${i}`} gap={g} />)}
            </div>
          </section>
        ))}
        {groupedGaps.length === 0 && (
          <div
            className="rounded-2xl p-8 text-center"
            style={{ backgroundColor: 'rgba(63,124,91,0.08)', border: '1px solid rgba(63,124,91,0.3)' }}
          >
            <CheckCircle2 className="w-7 h-7 mx-auto mb-3" style={{ color: '#3f7c5b' }} />
            <h2 className="text-lg mb-1" style={{ fontFamily: DISPLAY, color: INK }}>
              No required topics flagged.
            </h2>
            <p className="text-sm" style={{ color: MUTED }}>
              Your handbook covers everything we checked. Re-run after legislative updates.
            </p>
          </div>
        )}
      </div>

      {gap_counts.total_gaps > 0 && (
        <div
          className="mt-12 rounded-2xl p-8 text-center"
          style={{ backgroundColor: INK, color: BG }}
        >
          <ShieldCheck className="w-7 h-7 mx-auto mb-3" style={{ color: BG }} />
          <h2
            className="tracking-tight mb-2"
            style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: '1.6rem' }}
          >
            Fix every gap automatically.
          </h2>
          <p className="text-sm max-w-lg mx-auto mb-5" style={{ color: 'rgba(245,242,237,0.7)' }}>
            Matcha Lite generates the missing clauses, drops them into a clean handbook,
            and keeps it current as state laws change.
          </p>
          <Link
            to="/matcha-lite"
            className="inline-flex items-center px-6 h-11 rounded-full text-sm font-medium"
            style={{ backgroundColor: BG, color: INK }}
          >
            See Matcha Lite
          </Link>
        </div>
      )}

      {report.completed_at && (
        <p className="mt-12 text-[11px] text-center" style={{ color: MUTED }}>
          Completed {new Date(report.completed_at).toLocaleString()}. Informational only —
          not legal advice.
        </p>
      )}
    </>
  )
}

function severityRank(s: Severity): number {
  if (s === 'critical') return 0
  if (s === 'important') return 1
  return 2
}

function SeverityTile({
  icon: Icon,
  label,
  count,
  accent,
  help,
}: {
  icon: typeof AlertOctagon
  label: string
  count: number
  accent: string
  help: string
}) {
  return (
    <div
      className="rounded-2xl p-6"
      style={{ backgroundColor: 'rgba(255,255,255,0.5)', border: `1px solid ${LINE}` }}
    >
      <Icon className="w-5 h-5 mb-3" style={{ color: accent }} />
      <div
        className="tracking-tight mb-1"
        style={{ fontFamily: DISPLAY, fontWeight: 500, fontSize: '2.4rem', color: INK }}
      >
        {count}
      </div>
      <div className="text-[11px] uppercase tracking-[0.2em] mb-2" style={{ color: accent, fontFamily: 'var(--font-mono)' }}>
        {label}
      </div>
      <p className="text-xs" style={{ color: MUTED }}>{help}</p>
    </div>
  )
}

function GapCard({ gap }: { gap: Gap }) {
  const sevColor = gap.severity === 'critical' ? '#8a4a3a' : gap.severity === 'important' ? '#a47c2c' : '#5b6f7c'
  return (
    <div
      className="rounded-xl p-5"
      style={{
        backgroundColor: 'rgba(255,255,255,0.55)',
        border: `1px solid ${LINE}`,
        borderLeft: `3px solid ${sevColor}`,
      }}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-[15px] font-medium leading-snug" style={{ color: INK }}>
            {gap.requirement_title}
          </h3>
          {gap.what_good_looks_like && (
            <p className="text-sm mt-2 leading-relaxed" style={{ color: MUTED }}>
              {gap.what_good_looks_like}
            </p>
          )}
        </div>
        <span
          className="text-[10.5px] uppercase tracking-[0.18em] px-2 py-1 rounded-md whitespace-nowrap"
          style={{
            color: sevColor,
            backgroundColor: 'rgba(31,29,26,0.04)',
            border: `1px solid ${sevColor}`,
            fontFamily: 'var(--font-mono)',
          }}
        >
          {gap.severity}
        </span>
      </div>
      {(gap.citation || gap.matched_section_title) && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-3 text-[11px]" style={{ color: MUTED }}>
          {gap.citation && <span>cite · {gap.citation}</span>}
          {gap.matched_section_title && <span>matched · {gap.matched_section_title}</span>}
        </div>
      )}
    </div>
  )
}
