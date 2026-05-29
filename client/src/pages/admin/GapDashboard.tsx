/**
 * Persistent per-company Compliance Gap Analysis dashboard.
 *
 * Route: /admin/gap-analysis/company/:companyId
 *
 * This is the durable home for a company's compliance scope — for initial AND
 * continuous onboarding. It loads CHEAP (the backend re-resolves the persisted
 * scope against the current bank with no Gemini call, so gaps filled earlier
 * already show as covered) and offers two deliberate Gemini actions:
 *   • "Research" a gap (or selected gaps) → fills it into the bank (covered).
 *   • "Re-run analysis" → full role-aware enrichment (picks up new locations /
 *     roster changes flagged by the drift banner).
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft, Loader2, Play, Sparkles, RefreshCw, FileDown, FileText,
  CheckCircle2, AlertTriangle, XCircle, Search, MapPin, Scale, Users,
  FileSearch, CalendarCheck, Lightbulb, ChevronRight, ExternalLink,
} from 'lucide-react'
import { adminOnboarding } from '../../api/adminOnboarding'
import type {
  GapDashboardResponse, ResolvedScopeMissing, GapRequirementDetail,
} from '../../api/adminOnboarding'
import { useEnrichStream, type EnrichEvent } from '../../hooks/useEnrichStream'
import { useResearchGaps, type ResearchGapItem } from '../../hooks/useResearchGaps'
import GapCard, { humanizeCategory, jurisdictionLabel } from '../../features/admin-onboarding/GapCard'
import { complexityBandClass } from './GapOverview'

type CoveredItem = {
  requirement_id?: string
  category_slug?: string
  title?: string | null
  scope_level?: string
  city?: string | null
  county?: string | null
  state?: string | null
}

function missingId(m: ResolvedScopeMissing): string {
  return [m.category_slug, m.scope_level, m.state || '-', m.county || '-', m.city || '-'].join('::')
}

function toResearchItem(m: ResolvedScopeMissing): ResearchGapItem {
  return { category_slug: m.category_slug, scope_level: m.scope_level, state: m.state, county: m.county, city: m.city }
}

function eventStyle(type: string): { icon: React.ElementType; color: string; spin?: boolean } {
  switch (type) {
    case 'roster_scanned':
    case 'roles_detected': return { icon: Users, color: 'text-blue-400' }
    case 'jurisdiction_new': return { icon: MapPin, color: 'text-amber-400' }
    case 'jurisdiction_tracking': return { icon: CalendarCheck, color: 'text-emerald-400' }
    case 'researching':
    case 'repository_refresh':
    case 'retrying': return { icon: Search, color: 'text-violet-400', spin: true }
    case 'repository_refreshed':
    case 'started':
    case 'facility_inference': return { icon: FileSearch, color: 'text-violet-300' }
    case 'scoping': return { icon: Scale, color: 'text-blue-400' }
    case 'scoped':
    case 'complete': return { icon: CheckCircle2, color: 'text-emerald-400' }
    case 'warning':
    case 'repository_only': return { icon: AlertTriangle, color: 'text-amber-400' }
    case 'error': return { icon: XCircle, color: 'text-red-400' }
    default: return { icon: Sparkles, color: 'text-zinc-400' }
  }
}

function eventText(ev: EnrichEvent): string {
  if (ev.message) return ev.message
  if (ev.type === 'complete') return 'Analysis complete.'
  return ev.type.replace(/_/g, ' ')
}

function StatCard({ label, value, tone }: { label: string; value: number | string; tone?: 'gap' | 'ok' }) {
  const valueColor = tone === 'gap' ? 'text-amber-300' : tone === 'ok' ? 'text-emerald-300' : 'text-zinc-100'
  return (
    <div className="rounded-lg border border-vsc-border bg-vsc-panel p-3">
      <div className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${valueColor}`}>{value}</div>
    </div>
  )
}

function EventFeed({ events, running, label }: { events: EnrichEvent[]; running: boolean; label: string }) {
  const feedRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' })
  }, [events])
  if (!events.length && !running) return null
  return (
    <div ref={feedRef} className="rounded-xl border border-vsc-border bg-vsc-panel p-4 max-h-72 overflow-y-auto space-y-2">
      {events.filter((e) => e.type !== 'complete').map((ev, i) => {
        const { icon: Icon, color, spin } = eventStyle(ev.type)
        return (
          <div key={i} className="flex items-start gap-3 text-sm">
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
            </div>
          </div>
        )
      })}
      {running && (
        <div className="flex items-center gap-2 text-xs text-zinc-500 pt-1">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> {label}
        </div>
      )}
    </div>
  )
}

function CoveredRow({ companyId, item }: { companyId: string; item: CoveredItem }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<GapRequirementDetail | null>(null)
  const [loading, setLoading] = useState(false)

  function toggle() {
    const next = !open
    setOpen(next)
    if (next && !detail && item.requirement_id) {
      setLoading(true)
      adminOnboarding.getRequirementDetail(companyId, item.requirement_id)
        .then(setDetail).catch(() => {}).finally(() => setLoading(false))
    }
  }

  return (
    <div className="border-b border-vsc-border last:border-0">
      <button onClick={toggle} className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-vsc-bg/40">
        <ChevronRight className={`w-3.5 h-3.5 text-zinc-600 transition-transform ${open ? 'rotate-90' : ''}`} />
        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
        <span className="text-xs text-zinc-200 truncate">{item.title || humanizeCategory(item.category_slug || '')}</span>
        <span className="text-[10px] text-zinc-500 ml-auto shrink-0">{jurisdictionLabel(item)}</span>
      </button>
      {open && (
        <div className="px-9 pb-3 text-[11px] text-zinc-400 space-y-1">
          {loading && <span className="inline-flex items-center gap-1.5"><Loader2 className="w-3 h-3 animate-spin" /> loading…</span>}
          {detail && (
            <>
              {detail.current_value && <div><span className="text-zinc-500">Value: </span><span className="text-zinc-200 font-mono">{detail.current_value}</span>{detail.rate_type ? ` (${detail.rate_type})` : ''}</div>}
              {detail.description && <div className="leading-relaxed">{detail.description}</div>}
              {Array.isArray(detail.implementation_steps) && detail.implementation_steps.length > 0 && (
                <div className="pt-0.5">
                  <div className="text-zinc-500 mb-1">How to comply:</div>
                  <ol className="list-decimal pl-4 space-y-1 text-zinc-300 marker:text-vsc-accent">
                    {detail.implementation_steps.map((s, i) => <li key={i} className="leading-relaxed">{s}</li>)}
                  </ol>
                </div>
              )}
              {detail.effective_date && <div><span className="text-zinc-500">Effective: </span>{detail.effective_date}</div>}
              {detail.requires_written_policy && <div className="text-amber-300">Requires a written policy (handbook).</div>}
              {detail.source_url && (
                <a href={detail.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-emerald-300 hover:underline">
                  <ExternalLink className="w-3 h-3" /> {detail.source_name || 'Source'}
                </a>
              )}
              {!detail.description && !detail.current_value && <div className="text-zinc-500 italic">No additional detail recorded.</div>}
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default function GapDashboard() {
  const { companyId } = useParams<{ companyId: string }>()
  const [data, setData] = useState<GapDashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [activeResearch, setActiveResearch] = useState<string | null>(null) // 'bulk' | missingId
  const [showCovered, setShowCovered] = useState(false)
  const [showCx, setShowCx] = useState(false)

  const enrich = useEnrichStream()
  const research = useResearchGaps()

  const reload = useCallback(() => {
    if (!companyId) return
    return adminOnboarding.getGapDashboard(companyId)
      .then(setData).catch(() => {}).finally(() => setLoading(false))
  }, [companyId])

  useEffect(() => { void reload() }, [reload])
  // After a full re-run or a gap fill completes, reload (coverage up / gaps down).
  useEffect(() => { if (enrich.done) { void reload() } }, [enrich.done, reload])
  useEffect(() => {
    if (research.done) { void reload(); setSelected(new Set()); setActiveResearch(null) }
  }, [research.done, reload])

  if (!companyId) return null

  const busy = enrich.running || research.running

  function toggle(id: string) {
    setSelected((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id); else n.add(id)
      return n
    })
  }

  function researchOne(m: ResolvedScopeMissing) {
    setActiveResearch(missingId(m))
    void research.run(companyId!, [toResearchItem(m)])
  }

  function researchSelected() {
    const gaps = data?.dossier?.coverage.gaps ?? []
    const items = gaps.filter((m) => selected.has(missingId(m))).map(toResearchItem)
    if (items.length) { setActiveResearch('bulk'); void research.run(companyId!, items) }
  }

  // ── Loading ──
  if (loading) {
    return <div className="flex items-center justify-center py-24 text-zinc-500"><Loader2 className="animate-spin" size={22} /></div>
  }

  const dossier = data?.dossier
  const counts = dossier?.counts
  const gaps = dossier?.coverage.gaps ?? []
  const covered = (dossier?.coverage.covered ?? []) as CoveredItem[]
  const ambiguous = dossier?.coverage.ambiguous ?? []
  const suggestions = dossier?.ai_suggestions ?? {}
  const drift = data?.drift
  const jurisdictionCount = dossier?.scope.applicable_jurisdictions?.length ?? 0
  const coveragePct = counts?.coverage_pct ?? 0
  const cx = data?.complexity

  const suggestionCount =
    (suggestions.suggested_compliance_categories?.length ?? 0) +
    (suggestions.suggested_certifications?.length ?? 0) +
    (suggestions.suggested_licenses?.length ?? 0) +
    (suggestions.suggested_jurisdictions?.length ?? 0)

  // group gaps by jurisdiction
  const gapsByJur = new Map<string, ResolvedScopeMissing[]>()
  for (const g of gaps) {
    const k = jurisdictionLabel(g)
    if (!gapsByJur.has(k)) gapsByJur.set(k, [])
    gapsByJur.get(k)!.push(g)
  }
  // group covered by category
  const coveredByCat = new Map<string, CoveredItem[]>()
  for (const c of covered) {
    const k = humanizeCategory(c.category_slug || 'Other')
    if (!coveredByCat.has(k)) coveredByCat.set(k, [])
    coveredByCat.get(k)!.push(c)
  }

  const companyName = data?.company?.name || 'Company'
  const driftActive = !!drift && (drift.new_locations > 0 || drift.new_jurisdictions > 0)

  return (
    <div className="p-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-1">
        <Link to="/admin/gap-analysis" className="text-zinc-500 hover:text-zinc-300"><ArrowLeft size={18} /></Link>
        <Sparkles className="w-5 h-5 text-vsc-accent" />
        <h1 className="text-lg font-semibold text-zinc-100">Gap Analysis</h1>
        <span className="text-sm text-zinc-500">· {companyName}</span>
        {drift?.last_analyzed_at && (
          <span className="text-[11px] text-zinc-600 ml-2">last analyzed {new Date(drift.last_analyzed_at).toLocaleDateString()}</span>
        )}
        <div className="flex-1" />
        {data?.status === 'ok' && data.session_id && (
          <>
            <button onClick={() => adminOnboarding.downloadReportPdf(data.session_id!)} className="inline-flex items-center gap-1.5 px-2.5 h-8 rounded-md border border-vsc-border text-xs text-zinc-300 hover:bg-vsc-panel">
              <FileDown className="w-3.5 h-3.5" /> PDF
            </button>
            <button onClick={() => adminOnboarding.downloadReportMarkdown(data.session_id!)} className="inline-flex items-center gap-1.5 px-2.5 h-8 rounded-md border border-vsc-border text-xs text-zinc-300 hover:bg-vsc-panel">
              <FileText className="w-3.5 h-3.5" /> MD
            </button>
          </>
        )}
        <button
          onClick={() => void enrich.run(companyId)}
          disabled={busy}
          className="inline-flex items-center gap-2 px-3 h-8 rounded-md bg-vsc-accent text-vsc-bg text-xs font-medium hover:opacity-90 disabled:opacity-50"
        >
          {enrich.running ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          {enrich.running ? 'Analyzing…' : 'Re-run analysis'}
        </button>
      </div>
      <p className="text-xs text-zinc-500 mb-5 ml-9">
        Live compliance scope for this company. Fill gaps as you go — re-run when locations or roster change.
      </p>

      {enrich.error && <div className="mb-4 ml-9 rounded-md border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-300">{enrich.error}</div>}

      {/* never_run empty state */}
      {data?.status === 'never_run' && !enrich.running && !enrich.done && (
        <div className="ml-9 rounded-xl border border-vsc-border bg-vsc-panel p-8 text-center">
          <FileSearch className="w-8 h-8 text-zinc-600 mx-auto mb-3" />
          <h2 className="text-sm font-medium text-zinc-200">No gap analysis yet</h2>
          <p className="text-xs text-zinc-500 mt-1 mb-4 max-w-md mx-auto">
            Run the first analysis to scope this company's compliance + jurisdictional needs from its locations and employee roster.
          </p>
          <button onClick={() => void enrich.run(companyId)} className="inline-flex items-center gap-2 px-4 h-9 rounded-md bg-vsc-accent text-vsc-bg text-sm font-medium hover:opacity-90">
            <Play className="w-4 h-4" /> Run first analysis
          </button>
        </div>
      )}

      {/* re-run / first-run live feed */}
      {(enrich.running || (enrich.events.length > 0 && !enrich.done)) && (
        <div className="ml-9 mb-5"><EventFeed events={enrich.events} running={enrich.running} label="analyzing…" /></div>
      )}

      {/* Dashboard body */}
      {dossier && (
        <div className="space-y-5">
          {/* Stat row */}
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            <div className="rounded-lg border border-vsc-border bg-vsc-panel p-3 col-span-2 md:col-span-1">
              <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Coverage</div>
              <div className="text-2xl font-semibold text-zinc-100 mt-1">{coveragePct}%</div>
              <div className="mt-1.5 h-1.5 rounded-full bg-vsc-bg overflow-hidden">
                <div className="h-full rounded-full bg-emerald-500" style={{ width: `${coveragePct}%` }} />
              </div>
            </div>
            {cx && (
              <button
                onClick={() => setShowCx((v) => !v)}
                className="text-left rounded-lg border border-vsc-border bg-vsc-panel p-3 hover:border-zinc-600 transition-colors"
                title="Compliance complexity — click for breakdown"
              >
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider">Complexity</div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-2xl font-semibold text-zinc-100">{cx.score}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border uppercase tracking-wide ${complexityBandClass(cx.band)}`}>{cx.band}</span>
                </div>
              </button>
            )}
            <StatCard label="Covered" value={counts?.covered ?? 0} tone="ok" />
            <StatCard label="Gaps" value={counts?.gaps ?? 0} tone="gap" />
            <StatCard label="Ambiguous" value={counts?.ambiguous ?? 0} />
            <StatCard label="Jurisdictions" value={jurisdictionCount} />
          </div>

          {/* Complexity breakdown (expand from the card) */}
          {cx && showCx && (
            <div className="rounded-xl border border-vsc-border bg-vsc-panel p-4">
              <div className="text-sm font-semibold text-zinc-100 mb-3">
                Complexity breakdown — <span className="text-zinc-400 font-normal">{cx.score}/100 · {cx.band}</span>
              </div>
              <div className="space-y-2">
                {([
                  ['Domain risk', cx.breakdown.domain, 'what they do'],
                  ['Jurisdictional breadth', cx.breakdown.breadth, 'states & locales'],
                  ['Scale', cx.breakdown.scale, 'headcount'],
                  ['Requirement load', cx.breakdown.load, 'obligations'],
                ] as [string, number, string][]).map(([label, val, hint]) => (
                  <div key={label} className="flex items-center gap-3">
                    <div className="w-44 shrink-0 text-xs text-zinc-300">{label} <span className="text-zinc-600">· {hint}</span></div>
                    <div className="flex-1 h-2 rounded-full bg-vsc-bg overflow-hidden">
                      <div className="h-full rounded-full bg-vsc-accent" style={{ width: `${val}%` }} />
                    </div>
                    <span className="w-9 text-right text-xs text-zinc-400 tabular-nums">{val}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3 pt-3 border-t border-vsc-border text-[11px] text-zinc-500 flex flex-wrap gap-x-4 gap-y-1">
                {cx.breakdown.drivers.industry && <span>Industry: <span className="text-zinc-300">{cx.breakdown.drivers.industry}</span></span>}
                <span>{cx.breakdown.drivers.states} states · {cx.breakdown.drivers.jurisdictions} jurisdictions</span>
                <span>{cx.breakdown.drivers.headcount} employees</span>
                <span>{cx.breakdown.drivers.category_count} categories</span>
                <span>{cx.breakdown.drivers.requirement_count} requirements</span>
              </div>
            </div>
          )}

          {/* Drift banner */}
          {driftActive && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
              <div className="text-xs text-amber-200">
                {drift!.new_locations > 0 && <>{drift!.new_locations} new location{drift!.new_locations > 1 ? 's' : ''} </>}
                {drift!.new_locations > 0 && drift!.new_jurisdictions > 0 && '· '}
                {drift!.new_jurisdictions > 0 && <>{drift!.new_jurisdictions} roster jurisdiction{drift!.new_jurisdictions > 1 ? 's' : ''} not yet analyzed </>}
                — <button onClick={() => void enrich.run(companyId)} disabled={busy} className="font-medium underline hover:text-amber-100 disabled:opacity-50">Re-run analysis</button> to refresh.
              </div>
            </div>
          )}

          {/* Gaps — the core */}
          <div className="rounded-xl border border-vsc-border bg-vsc-panel/40 p-4">
            <div className="flex items-center justify-between gap-3 mb-3">
              <h2 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
                <Search className="w-4 h-4 text-amber-400" /> Gaps — need research ({gaps.length})
              </h2>
              {gaps.length > 0 && (
                <button
                  onClick={researchSelected}
                  disabled={busy || selected.size === 0}
                  className="text-xs px-3 py-1.5 rounded-lg bg-vsc-accent text-vsc-bg font-medium hover:opacity-90 disabled:opacity-40 inline-flex items-center gap-2"
                >
                  {research.running && activeResearch === 'bulk' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                  Research selected ({selected.size})
                </button>
              )}
            </div>

            {gaps.length === 0 ? (
              <div className="text-center py-6 text-sm text-emerald-300 flex items-center justify-center gap-2">
                <CheckCircle2 className="w-4 h-4" /> No open gaps — every scoped requirement is covered.
              </div>
            ) : (
              <div className="space-y-4">
                {[...gapsByJur.entries()].map(([jur, items]) => (
                  <div key={jur}>
                    <div className="flex items-center gap-1.5 text-[11px] text-zinc-500 uppercase tracking-wide mb-1.5">
                      <MapPin className="w-3 h-3" /> {jur} · {items.length}
                    </div>
                    <div className="space-y-2">
                      {items.map((m) => {
                        const id = missingId(m)
                        return (
                          <GapCard
                            key={id}
                            gap={m}
                            selected={selected.has(id)}
                            onToggle={() => toggle(id)}
                            onResearch={() => researchOne(m)}
                            researching={research.running && activeResearch === id}
                            disabled={busy}
                          />
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {research.running && (
              <div className="mt-3 border-t border-vsc-border pt-3">
                <EventFeed events={research.events} running={research.running} label="researching…" />
              </div>
            )}
            {research.error && <p className="text-xs text-red-400 mt-2">{research.error}</p>}
          </div>

          {/* AI safety net */}
          {suggestionCount > 0 && (
            <div className="rounded-xl border border-vsc-border bg-vsc-panel p-4">
              <h2 className="text-sm font-semibold text-zinc-100 flex items-center gap-2 mb-2">
                <Lightbulb className="w-4 h-4 text-amber-400" /> AI safety net ({suggestionCount})
              </h2>
              {suggestions.summary && <p className="text-[11px] text-zinc-500 mb-2 leading-relaxed">{suggestions.summary}</p>}
              <div className="flex flex-wrap gap-1.5">
                {suggestions.suggested_compliance_categories?.map((c) => (
                  <span key={`c-${c.category_slug}`} className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-vsc-border">{humanizeCategory(c.category_slug)} · {c.scope}</span>
                ))}
                {suggestions.suggested_certifications?.map((c) => (
                  <span key={`ct-${c.slug}`} className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-vsc-border">{c.name}</span>
                ))}
                {suggestions.suggested_licenses?.map((l) => (
                  <span key={`l-${l.slug}`} className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-vsc-border">{l.name}</span>
                ))}
                {suggestions.suggested_jurisdictions?.map((j, i) => (
                  <span key={`j-${i}`} className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-vsc-border">{jurisdictionLabel(j)}</span>
                ))}
              </div>
              <p className="text-[10px] text-zinc-600 mt-2">Advisory — re-run analysis to fold confirmed items into scope.</p>
            </div>
          )}

          {/* Ambiguous */}
          {ambiguous.length > 0 && (
            <div className="rounded-xl border border-vsc-border bg-vsc-panel p-4">
              <h2 className="text-sm font-semibold text-zinc-100 flex items-center gap-2 mb-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" /> Ambiguous — need disambiguation ({ambiguous.length})
              </h2>
              <div className="space-y-1.5">
                {ambiguous.map((a, i) => (
                  <div key={i} className="text-xs text-zinc-400">
                    <span className="text-zinc-200">{humanizeCategory(a.category_slug)}</span>
                    {a.why ? <span className="text-zinc-500"> — {a.why}</span> : null}
                    <span className="text-zinc-600"> ({a.candidates?.length ?? 0} candidates)</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Covered (collapsible) */}
          <div className="rounded-xl border border-vsc-border bg-vsc-panel">
            <button onClick={() => setShowCovered((v) => !v)} className="w-full flex items-center gap-2 px-4 py-3 text-left">
              <ChevronRight className={`w-4 h-4 text-zinc-500 transition-transform ${showCovered ? 'rotate-90' : ''}`} />
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span className="text-sm font-semibold text-zinc-100">Already covered ({covered.length})</span>
            </button>
            {showCovered && (
              <div className="px-2 pb-2">
                {covered.length === 0 ? (
                  <p className="text-xs text-zinc-500 px-2 py-3">Nothing covered yet — research the gaps above.</p>
                ) : (
                  [...coveredByCat.entries()].map(([cat, items]) => (
                    <div key={cat} className="mb-2">
                      <div className="text-[11px] text-zinc-500 uppercase tracking-wide px-3 pt-2 pb-1">{cat} · {items.length}</div>
                      <div className="rounded-lg border border-vsc-border overflow-hidden">
                        {items.map((c, i) => <CoveredRow key={c.requirement_id || i} companyId={companyId} item={c} />)}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
