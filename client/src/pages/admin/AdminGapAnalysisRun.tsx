/**
 * Master-admin gap-analysis enrichment run for an EXISTING company.
 *
 * The performative "Sync Employees → Gap Analysis" view: streams staged events
 * (roster scan → new jurisdiction discovery → live research → role-aware scope)
 * so it visibly "scopes out" the compliance/jurisdictional apparatus.
 * Route: /admin/onboarding/company/:companyId
 */
import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft, Loader2, Play, Users, Briefcase, MapPin, CalendarCheck,
  Search, Scale, CheckCircle2, AlertTriangle, XCircle, Sparkles, FileSearch,
} from 'lucide-react'
import { api } from '../../api/client'
import { useEnrichStream, type EnrichEvent } from '../../hooks/useEnrichStream'

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
        <Link to="/admin/onboarding" className="text-zinc-500 hover:text-zinc-300 transition-colors">
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
        className="ml-9 inline-flex items-center gap-2 px-4 h-9 rounded-md bg-emerald-500/90 hover:bg-emerald-500 text-zinc-950 text-sm font-medium disabled:opacity-50 transition-colors"
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
          className="mt-5 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 max-h-[460px] overflow-y-auto space-y-2"
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
              <div key={label as string} className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
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
              to={`/admin/onboarding/${done.session_id}`}
              className="inline-block mt-4 text-[11px] font-medium text-emerald-400 hover:text-emerald-300"
            >
              View full gap analysis →
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
