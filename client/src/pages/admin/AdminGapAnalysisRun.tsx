/**
 * Master-admin gap-analysis enrichment run for an EXISTING company.
 *
 * The performative "Sync Employees → Gap Analysis" view: streams staged events
 * (roster scan → new jurisdiction discovery → live research → role-aware scope)
 * so it visibly "scopes out" the compliance/jurisdictional apparatus.
 * Route: /admin/gap-analysis/company/:companyId
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft, Loader2, Play, Users, Briefcase, MapPin, CalendarCheck,
  Search, Scale, CheckCircle2, AlertTriangle, XCircle, Sparkles, FileSearch,
  Square, CheckSquare, FlaskConical, Lightbulb,
} from 'lucide-react'
import { api } from '../../api/client'
import { adminOnboarding } from '../../api/adminOnboarding'
import type { ResolvedScope, ResolvedScopeMissing, GapCheckResult } from '../../api/adminOnboarding'
import { useEnrichStream, type EnrichEvent } from '../../hooks/useEnrichStream'
import { useResearchGaps, type ResearchGapItem } from '../../hooks/useResearchGaps'

type IconDef = { icon: React.ElementType; color: string; spin?: boolean }

function eventStyle(type: string): IconDef {
  switch (type) {
    case 'roster_scanned': return { icon: Users, color: 'text-blue-400' }
    case 'roles_detected': return { icon: Briefcase, color: 'text-blue-400' }
    case 'jurisdiction_new': return { icon: MapPin, color: 'text-amber-400' }
    case 'jurisdiction_tracking': return { icon: CalendarCheck, color: 'text-emerald-400' }
    case 'researching':
    case 'repository_refresh':
    case 'retrying': return { icon: Search, color: 'text-violet-400', spin: true }
    case 'repository_refreshed':
    case 'started':
    case 'facility_inference': return { icon: FileSearch, color: 'text-violet-300' }
    case 'scoping': return { icon: Scale, color: 'text-blue-400' }
    case 'scoped': return { icon: Sparkles, color: 'text-emerald-400' }
    case 'complete': return { icon: CheckCircle2, color: 'text-emerald-400' }
    case 'warning':
    case 'repository_only': return { icon: AlertTriangle, color: 'text-amber-400' }
    case 'error': return { icon: XCircle, color: 'text-red-400' }
    default: return { icon: Sparkles, color: 'text-zinc-400' }
  }
}

function eventText(ev: EnrichEvent): string {
  if (ev.message) return ev.message
  switch (ev.type) {
    case 'started': return `Checking ${ev.jurisdiction ?? 'jurisdiction'}…`
    case 'complete': return 'Gap analysis complete.'
    default: return ev.type.replace(/_/g, ' ')
  }
}

export default function AdminGapAnalysisRun() {
  const { companyId } = useParams<{ companyId: string }>()
  const [companyName, setCompanyName] = useState<string>('')
  const { running, events, done, error, run } = useEnrichStream()
  const feedRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!companyId) return
    api.get<{ name: string }>(`/admin/companies/${companyId}`)
      .then((r) => setCompanyName(r.name))
      .catch(() => setCompanyName(''))
  }, [companyId])

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' })
  }, [events])

  if (!companyId) return null

  return (
    <div className="p-6 max-w-3xl">
      <div className="flex items-center gap-3 mb-1">
        <Link to="/admin/gap-analysis" className="text-zinc-500 hover:text-zinc-300 transition-colors">
          <ArrowLeft size={18} />
        </Link>
        <Sparkles className="w-5 h-5 text-emerald-400" />
        <h1 className="text-lg font-semibold text-zinc-100">Gap Analysis</h1>
        <span className="text-sm text-zinc-500">· {companyName || 'company'}</span>
      </div>
      <p className="text-xs text-zinc-500 mb-5 ml-9">
        Pull this company's live employee roster, discover work jurisdictions the compliance
        engine isn't tracking yet, research them, and scope role-specific requirements.
      </p>

      <button
        onClick={() => void run(companyId)}
        disabled={running}
        className="ml-9 inline-flex items-center gap-2 px-4 h-9 rounded-md bg-vsc-accent text-vsc-bg hover:opacity-90 text-sm font-medium disabled:opacity-50 transition-colors"
      >
        {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
        {running ? 'Running…' : events.length ? 'Re-run gap analysis' : 'Run gap analysis'}
      </button>

      {error && (
        <div className="mt-4 ml-9 rounded-md border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {events.length > 0 && (
        <div
          ref={feedRef}
          className="mt-5 rounded-xl border border-vsc-border bg-vsc-panel p-4 max-h-[460px] overflow-y-auto space-y-2"
        >
          {events.filter((e) => e.type !== 'complete').map((ev, i) => {
            const { icon: Icon, color, spin } = eventStyle(ev.type)
            return (
              <div key={i} className="flex items-start gap-3 text-sm animate-[fadeIn_0.2s_ease-out]">
                <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${color} ${spin ? 'animate-pulse' : ''}`} />
                <div className="flex-1 min-w-0">
                  <span className="text-zinc-300">{eventText(ev)}</span>
                  {ev.type === 'roles_detected' && ev.roles && ev.roles.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {ev.roles.map((r) => (
                        <span key={r} className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20">{r}</span>
                      ))}
                    </div>
                  )}
                  {ev.missing_categories && ev.missing_categories.length > 0 && (
                    <div className="text-[11px] text-zinc-500 mt-0.5">
                      {ev.missing_categories.join(', ')}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
          {running && (
            <div className="flex items-center gap-2 text-xs text-zinc-500 pt-1">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> working…
            </div>
          )}
        </div>
      )}

      {done && (
        <div className="mt-5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-5">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            <h2 className="text-sm font-semibold text-emerald-200">Gap analysis complete</h2>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              ['New jurisdictions', done.new_jurisdictions?.length ?? 0],
              ['Roles', done.roles?.length ?? 0],
              ['Covered', done.covered ?? 0],
              ['Gaps', done.missing ?? 0],
            ].map(([label, value]) => (
              <div key={label as string} className="rounded-lg border border-vsc-border bg-vsc-panel p-3">
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</div>
                <div className="text-xl font-semibold text-zinc-100 mt-1">{value}</div>
              </div>
            ))}
          </div>
          {done.new_jurisdictions && done.new_jurisdictions.length > 0 && (
            <p className="text-[11px] text-zinc-400 mt-3 flex items-start gap-2">
              <MapPin className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
              <span>{done.new_jurisdictions.map((j) => `${j.city ? `${j.city}, ` : ''}${j.state}`).join(' · ')}</span>
            </p>
          )}
          {done.session_id && (
            <Link
              to={`/admin/gap-analysis/${done.session_id}`}
              className="inline-block mt-4 text-[11px] font-medium text-emerald-400 hover:text-emerald-300"
            >
              View full gap analysis →
            </Link>
          )}
        </div>
      )}

      {done?.session_id && <GapsToFill companyId={companyId} sessionId={done.session_id} />}
    </div>
  )
}


// ── Gaps to fill (selective research) ────────────────────────────────────────

function missingId(m: ResolvedScopeMissing): string {
  return [m.category_slug, m.scope_level, m.state || '-', m.county || '-', m.city || '-'].join('::')
}

function jLabel(m: { city?: string | null; state?: string | null }): string {
  return `${m.city ? `${m.city}, ` : ''}${m.state || 'federal'}`
}

function GapsToFill({ companyId, sessionId }: { companyId: string; sessionId: string }) {
  const [missing, setMissing] = useState<ResolvedScopeMissing[]>([])
  const [gapCheck, setGapCheck] = useState<GapCheckResult | null>(null)
  const [thin, setThin] = useState<string[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const { running, events, done, error, run } = useResearchGaps()
  const feedRef = useRef<HTMLDivElement>(null)

  const load = useCallback(() => {
    adminOnboarding.getSession(sessionId).then((s) => {
      const rs = s.resolved_scope as (ResolvedScope & { gap_check?: GapCheckResult }) | null
      setMissing(rs?.missing ?? [])
      setGapCheck(rs?.gap_check ?? null)
      const nudges: string[] = []
      const b = s.basics ?? {}
      if (!b.industry || b.industry === 'general') nudges.push('industry')
      if (!b.description) nudges.push('business description')
      if (!s.locations || s.locations.length === 0) nudges.push('work locations')
      setThin(nudges)
    }).catch(() => {})
  }, [sessionId])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' })
  }, [events])
  // After a fill run completes, reload (coverage up, missing down) + clear selection.
  useEffect(() => { if (done) { load(); setSelected(new Set()) } }, [done, load])

  function toggle(id: string) {
    setSelected((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id); else n.add(id)
      return n
    })
  }

  function researchSelected() {
    const items: ResearchGapItem[] = missing
      .filter((m) => selected.has(missingId(m)))
      .map((m) => ({
        category_slug: m.category_slug, scope_level: m.scope_level,
        state: m.state, county: m.county, city: m.city,
      }))
    if (items.length) void run(companyId, items)
  }

  const suggestionCount =
    (gapCheck?.suggested_compliance_categories?.length ?? 0) +
    (gapCheck?.suggested_certifications?.length ?? 0) +
    (gapCheck?.suggested_licenses?.length ?? 0) +
    (gapCheck?.suggested_jurisdictions?.length ?? 0)

  return (
    <div className="mt-5 space-y-4">
      {thin.length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
          <div className="text-xs text-amber-200">
            Thin profile — fill in <span className="font-medium">{thin.join(', ')}</span> on the
            company record for sharper analysis.
          </div>
        </div>
      )}

      {missing.length > 0 && (
        <div className="rounded-xl border border-vsc-border bg-vsc-panel p-4">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div className="flex items-center gap-2">
              <FlaskConical className="w-4 h-4 text-violet-400" />
              <h3 className="text-sm font-medium text-zinc-200">Gaps to fill ({missing.length})</h3>
            </div>
            <button
              onClick={researchSelected}
              disabled={running || selected.size === 0}
              className="text-xs px-3 py-1.5 rounded-lg bg-violet-600 text-white font-medium hover:bg-violet-500 disabled:opacity-40 inline-flex items-center gap-2"
            >
              {running ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
              Research selected ({selected.size})
            </button>
          </div>
          <p className="text-[11px] text-zinc-500 mb-2">
            Pick which gaps to research — only the selected ones run, so it stays fast.
          </p>
          <div className="space-y-1 max-h-60 overflow-y-auto">
            {missing.map((m) => {
              const id = missingId(m)
              const on = selected.has(id)
              return (
                <button
                  key={id}
                  onClick={() => toggle(id)}
                  disabled={running}
                  className="w-full flex items-center gap-2 text-left px-2 py-1.5 rounded hover:bg-vsc-panel disabled:opacity-50"
                >
                  {on ? <CheckSquare className="w-4 h-4 text-violet-400 shrink-0" /> : <Square className="w-4 h-4 text-zinc-600 shrink-0" />}
                  <span className="text-xs text-zinc-300">{m.category_slug.replace(/_/g, ' ')}</span>
                  <span className="text-[10px] text-zinc-500 ml-auto">{jLabel(m)}</span>
                </button>
              )
            })}
          </div>

          {events.length > 0 && (
            <div ref={feedRef} className="mt-3 border-t border-vsc-border pt-3 max-h-48 overflow-y-auto space-y-1.5">
              {events.filter((e) => e.type !== 'complete').map((ev, i) => {
                const { icon: Icon, color, spin } = eventStyle(ev.type)
                return (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <Icon className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${color} ${spin ? 'animate-pulse' : ''}`} />
                    <span className="text-zinc-400">{eventText(ev)}</span>
                  </div>
                )
              })}
              {running && (
                <div className="flex items-center gap-2 text-[11px] text-zinc-500">
                  <Loader2 className="w-3 h-3 animate-spin" /> researching…
                </div>
              )}
            </div>
          )}
          {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
        </div>
      )}

      {suggestionCount > 0 && (
        <div className="rounded-xl border border-vsc-border bg-vsc-panel p-4">
          <div className="flex items-center gap-2 mb-2">
            <Lightbulb className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-medium text-zinc-200">AI suggestions ({suggestionCount})</h3>
          </div>
          {gapCheck?.summary && <p className="text-[11px] text-zinc-500 mb-2">{gapCheck.summary}</p>}
          <div className="flex flex-wrap gap-1.5">
            {gapCheck?.suggested_compliance_categories?.map((c) => (
              <span key={`c-${c.category_slug}`} className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-vsc-border">
                {c.category_slug.replace(/_/g, ' ')} · {c.scope}
              </span>
            ))}
            {gapCheck?.suggested_licenses?.map((l) => (
              <span key={`l-${l.slug}`} className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-vsc-border">
                {l.name}
              </span>
            ))}
            {gapCheck?.suggested_jurisdictions?.map((j, i) => (
              <span key={`j-${i}`} className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-vsc-border">
                {jLabel(j)}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
