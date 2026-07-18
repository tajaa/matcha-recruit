import { useEffect, useMemo, useRef } from 'react'
import {
  AlertTriangle, BookOpen, CheckCircle2, FileSearch, Landmark, Loader2,
  MapPin, Play, Scale, Search, Sparkles, XCircle, Zap,
} from 'lucide-react'
import { useMatchaXBuildStream, type BuildEvent, type HandbookGrade } from './useMatchaXBuildStream'

type Phase = 'pending' | 'building' | 'built'
type Tiers = { federal: boolean; state: boolean; county: boolean; city: boolean }
type LocCard = {
  label: string
  city?: string | null
  state?: string
  phase: Phase
  covered: number
  codifiedNew: number
  researchedLive: boolean
  tiers: Tiers
}
type StateCoverage = { state: string; coveredCount: number; gapCount: number; gaps: HandbookGrade[] }

const TIER_EVENTS_STATE = ['tier1', 'repository', 'repository_refreshed', 'facility_inference', 'fallback', 'started']
const TIER_EVENTS_LOCAL = ['researching', 'repository_refresh', 'discovering_sources', 'retrying']

function reduceBuild(events: BuildEvent[]) {
  const map = new Map<string, LocCard>()
  const order: string[] = []
  const handbook: StateCoverage[] = []
  const gradingStates = new Set<string>()

  const seed = (label: string, phase: Phase): LocCard => {
    let c = map.get(label)
    if (!c) {
      c = { label, phase, covered: 0, codifiedNew: 0, researchedLive: false,
        tiers: { federal: false, state: false, county: false, city: false } }
      map.set(label, c)
      order.push(label)
    }
    return c
  }

  for (const ev of events) {
    if (ev.type === 'locations_scanned' && ev.labels) {
      for (const lb of ev.labels) seed(lb, 'pending')
      continue
    }
    if (ev.type === 'handbook_grading' && ev.state) { gradingStates.add(ev.state); continue }
    if (ev.type === 'handbook_coverage' && ev.state) {
      gradingStates.delete(ev.state)
      handbook.push({ state: ev.state, coveredCount: ev.covered_count ?? 0, gapCount: ev.gap_count ?? 0, gaps: ev.gaps ?? [] })
      continue
    }
    const label = ev.label
    if (!label) continue
    const c = seed(label, 'building')
    if (ev.city !== undefined) c.city = ev.city
    if (ev.state) c.state = ev.state
    if (ev.type === 'location_start') { c.phase = 'building'; c.tiers.federal = true }
    if (TIER_EVENTS_STATE.includes(ev.type)) { c.tiers.federal = true; c.tiers.state = true }
    if (TIER_EVENTS_LOCAL.includes(ev.type)) { c.researchedLive = true; c.tiers.state = true; c.tiers.county = true; c.tiers.city = true }
    if (ev.type === 'location_built') {
      c.phase = 'built'
      c.covered = typeof ev.covered === 'number' ? ev.covered : c.covered
      c.codifiedNew = ev.codified_new ?? 0
      if (ev.researched_live) c.researchedLive = true
      c.tiers.federal = true
      c.tiers.state = true
    }
  }
  return { cards: order.map((l) => map.get(l)!).filter(Boolean), handbook, gradingStates }
}

export default function Step4Build({ handbookUrl, onDone }: { handbookUrl: string | null; onDone: () => void }) {
  const { running, events, done, error, totals, run } = useMatchaXBuildStream()
  const { cards, handbook, gradingStates } = useMemo(() => reduceBuild(events), [events])

  const started = running || events.length > 0 || !!done

  // Hero (pre-start) — the operator hits "Build" so the demo plays on cue.
  if (!started) {
    return (
      <div className="text-center py-12 space-y-6">
        <div className="mx-auto w-14 h-14 rounded-2xl bg-emerald-900/40 ring-1 ring-emerald-800 flex items-center justify-center">
          <Zap className="w-7 h-7 text-emerald-400" />
        </div>
        <div>
          <h2 className="text-xl font-semibold text-zinc-100">Build your compliance baseline</h2>
          <p className="text-sm text-zinc-400 mt-2 max-w-md mx-auto">
            We'll resolve each location's jurisdiction, pull what we have on file, research and
            codify anything new live, and {handbookUrl ? 'grade your handbook against each state.' : 'map your baseline.'}
            {' '}Watch it happen.
          </p>
        </div>
        <button
          onClick={() => run(handbookUrl)}
          className="inline-flex items-center gap-2 bg-emerald-700 hover:bg-emerald-600 text-white font-medium px-6 py-2.5 rounded-lg transition-colors"
        >
          <Play className="w-4 h-4" /> Start the build
        </button>
      </div>
    )
  }

  const coveragePct = done?.handbook_coverage_pct ?? (
    totals.handbookCovered + totals.handbookGaps > 0
      ? Math.round((100 * totals.handbookCovered) / (totals.handbookCovered + totals.handbookGaps))
      : null
  )

  return (
    <div className="space-y-5">
      {/* Live header totals */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        <Stat label="Locations" value={done?.locations ?? totals.locationsBuilt} />
        <Stat label="Jurisdictions" value={done?.jurisdictions ?? totals.jurisdictions} />
        <Stat label="Requirements" value={done?.requirements ?? totals.requirements} tone="ok" />
        <Stat label="Newly codified" value={done?.codified_new ?? totals.codifiedNew} tone="accent" />
        <Stat label="Handbook" value={coveragePct === null ? '—' : `${coveragePct}%`} tone="ok" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        {/* Left: location cards */}
        <div className="space-y-3">
          {cards.map((c) => (
            <LocationCard key={c.label} card={c} />
          ))}
          {handbook.length > 0 || gradingStates.size > 0 ? (
            <HandbookPanel coverage={handbook} grading={gradingStates} />
          ) : null}
        </div>

        {/* Right: narrated feed */}
        <EventFeed events={events} running={running} />
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-400">
          <XCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {done && (
        <div className="rounded-xl border border-emerald-800 bg-emerald-950/30 p-5 text-center space-y-3">
          <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto" />
          <div>
            <h3 className="text-lg font-semibold text-zinc-100">Your compliance baseline is live</h3>
            <p className="text-sm text-zinc-400 mt-1">
              {done.requirements ?? 0} requirement(s) mapped across {done.locations ?? 0} location(s) and{' '}
              {done.jurisdictions ?? 0} jurisdiction(s)
              {done.codified_new ? `, ${done.codified_new} newly codified into your directory` : ''}
              {coveragePct !== null ? ` · ${coveragePct}% handbook coverage` : ''}.
              {done.roster_locations_added ? (
                <span className="block mt-1">
                  {done.roster_locations_added} location(s) added from your employee roster.
                </span>
              ) : null}
              {done.skipped_no_work_state ? (
                <span className="block mt-1 text-amber-500">
                  {done.skipped_no_work_state} employee(s) have no work state on file — their
                  jurisdiction may be missing from this build.
                </span>
              ) : null}
            </p>
          </div>
          <button
            onClick={onDone}
            className="inline-flex items-center gap-2 bg-emerald-700 hover:bg-emerald-600 text-white font-medium px-5 py-2 rounded-lg transition-colors"
          >
            Continue →
          </button>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: 'ok' | 'accent' }) {
  const color = tone === 'ok' ? 'text-emerald-300' : tone === 'accent' ? 'text-violet-300' : 'text-zinc-100'
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
      <div className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</div>
      <div className={`text-xl font-semibold mt-0.5 tabular-nums ${color}`}>{value}</div>
    </div>
  )
}

function HierarchyChips({ tiers }: { tiers: Tiers }) {
  const items: { key: keyof Tiers; label: string }[] = [
    { key: 'federal', label: 'Federal' },
    { key: 'state', label: 'State' },
    { key: 'county', label: 'County' },
    { key: 'city', label: 'City' },
  ]
  return (
    <div className="flex items-center gap-1.5">
      {items.map((it) => (
        <span
          key={it.key}
          className={
            'text-[10px] px-1.5 py-0.5 rounded border transition-colors duration-500 ' +
            (tiers[it.key]
              ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
              : 'bg-zinc-900 text-zinc-600 border-zinc-800')
          }
        >
          {it.label}
        </span>
      ))}
    </div>
  )
}

function LocationCard({ card }: { card: LocCard }) {
  const active = card.phase === 'building'
  const built = card.phase === 'built'
  return (
    <div
      className={
        'rounded-xl border p-4 transition-all duration-300 ' +
        (built
          ? 'border-zinc-800 bg-zinc-900/40'
          : active
            ? 'border-emerald-800/70 bg-emerald-950/10 ring-1 ring-emerald-900/50'
            : 'border-zinc-800 bg-zinc-900/20 opacity-70')
      }
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <MapPin className={`w-4 h-4 shrink-0 ${built ? 'text-emerald-500' : active ? 'text-emerald-400' : 'text-zinc-600'}`} />
          <span className="text-sm font-medium text-zinc-100 truncate">{card.label}</span>
        </div>
        {active && <Loader2 className="w-4 h-4 text-emerald-400 animate-spin shrink-0" />}
        {built && <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />}
      </div>

      <div className="mt-3">
        <HierarchyChips tiers={card.tiers} />
      </div>

      <div className="mt-3 flex items-center gap-3 text-xs">
        {card.researchedLive && !built && (
          <span className="flex items-center gap-1 text-violet-300">
            <Search className="w-3.5 h-3.5 animate-pulse" /> researching live…
          </span>
        )}
        {built && (
          <>
            <span className="text-zinc-400">{card.covered} requirement(s) mapped</span>
            {card.codifiedNew > 0 && (
              <span className="flex items-center gap-1 text-violet-300">
                <Sparkles className="w-3.5 h-3.5" /> {card.codifiedNew} newly codified
              </span>
            )}
          </>
        )}
        {card.phase === 'pending' && <span className="text-zinc-600">queued…</span>}
      </div>
    </div>
  )
}

function HandbookPanel({ coverage, grading }: { coverage: StateCoverage[]; grading: Set<string> }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-zinc-200">
        <BookOpen className="w-4 h-4 text-blue-400" /> Handbook coverage
      </div>
      {[...grading].map((st) => (
        <div key={st} className="flex items-center gap-2 text-xs text-zinc-400">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400" /> Grading against {st} law…
        </div>
      ))}
      {coverage.map((c) => {
        const total = c.coveredCount + c.gapCount
        const pct = total ? Math.round((100 * c.coveredCount) / total) : 0
        return (
          <div key={c.state} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-300 font-medium">{c.state}</span>
              <span className="text-zinc-500">
                <span className="text-emerald-400">{c.coveredCount} covered</span>
                {c.gapCount > 0 && <span className="text-amber-400"> · {c.gapCount} gap(s)</span>}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
              <div className="h-full bg-emerald-500 transition-all duration-700" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Narrated event feed (BuildEvent flavour of GapDashboard's EventFeed) ──

function eventStyle(type: string): { icon: React.ElementType; color: string; spin?: boolean } {
  switch (type) {
    case 'started':
    case 'locations_scanned': return { icon: FileSearch, color: 'text-violet-300' }
    case 'location_start': return { icon: MapPin, color: 'text-amber-400' }
    case 'researching':
    case 'repository_refresh':
    case 'discovering_sources':
    case 'retrying': return { icon: Search, color: 'text-violet-400', spin: true }
    case 'tier1':
    case 'repository':
    case 'repository_refreshed':
    case 'facility_inference':
    case 'fallback': return { icon: Landmark, color: 'text-blue-300' }
    case 'location_built': return { icon: CheckCircle2, color: 'text-emerald-400' }
    case 'handbook_detected':
    case 'handbook_grading': return { icon: Scale, color: 'text-blue-400', spin: true }
    case 'handbook_coverage':
    case 'complete': return { icon: CheckCircle2, color: 'text-emerald-400' }
    case 'handbook_skipped':
    case 'warning':
    case 'repository_only': return { icon: AlertTriangle, color: 'text-amber-400' }
    case 'error': return { icon: XCircle, color: 'text-red-400' }
    default: return { icon: Sparkles, color: 'text-zinc-400' }
  }
}

function EventFeed({ events, running }: { events: BuildEvent[]; running: boolean }) {
  const feedRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' })
  }, [events])
  return (
    <div ref={feedRef} className="rounded-xl border border-zinc-800 bg-zinc-950 p-4 max-h-[28rem] overflow-y-auto space-y-2">
      {events.filter((e) => e.type !== 'complete').map((ev, i) => {
        const { icon: Icon, color, spin } = eventStyle(ev.type)
        return (
          <div key={i} className="flex items-start gap-3 text-sm">
            <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${color} ${spin ? 'animate-pulse' : ''}`} />
            <span className="text-zinc-300 min-w-0">{ev.message || ev.type.replace(/_/g, ' ')}</span>
          </div>
        )
      })}
      {running && (
        <div className="flex items-center gap-2 text-xs text-zinc-500 pt-1">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> building…
        </div>
      )}
    </div>
  )
}
