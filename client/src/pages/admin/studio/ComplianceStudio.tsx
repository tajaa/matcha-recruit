import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Compass, Layers, Library, MessageCircle, Sparkles, Workflow } from 'lucide-react'
import { api } from '../../../api/client'
import CommandCenter from './CommandCenter'
import PipelineTab from './PipelineTab'
import CoverageTab from './CoverageTab'
import AuthorityTab from './AuthorityTab'
import LibraryTab from './LibraryTab'
import StudioAssistant from './StudioAssistant'
import type { GotoParams, StudioView, UncodifiedItem, Worklist } from './types'

const TABS: { id: StudioView; label: string; icon: typeof Compass }[] = [
  { id: 'home', label: 'Home', icon: Compass },
  { id: 'pipeline', label: 'Pipeline', icon: Workflow },
  { id: 'coverage', label: 'Coverage', icon: Sparkles },
  { id: 'authority', label: 'Authority', icon: Layers },
  { id: 'library', label: 'Library', icon: Library },
]

// One studio for the whole compliance library. It grows through two funnels
// into one repository — SUPPLY (Authority tab: scope → ingest → classify →
// confirm → codify) and DEMAND (Pipeline tab: a company's gap → coverage
// request → research → review → approve → codify). Codification is what makes
// the data AUTHORITATIVE; scoping is what makes it EXHAUSTIVE. Home is the
// Command Center — a single prioritized worklist merging both funnels so the
// admin always knows what needs them next, instead of hunting across tabs.
export default function ComplianceStudio() {
  const [searchParams, setSearchParams] = useSearchParams()
  const view = (searchParams.get('view') as StudioView) || 'home'

  const [worklist, setWorklist] = useState<Worklist | null>(null)
  const [worklistLoading, setWorklistLoading] = useState(true)
  const [assistantOpen, setAssistantOpen] = useState(false)

  // Seeded items when the Command Center routes into Pipeline with specific
  // uncodified rows to walk through (not a fresh post-approve batch).
  const [seedUncodified, setSeedUncodified] = useState<UncodifiedItem[] | null>(null)

  const fetchWorklist = useCallback(async () => {
    setWorklistLoading(true)
    try { setWorklist(await api.get<Worklist>('/admin/studio/worklist')) }
    catch { setWorklist(null) }
    finally { setWorklistLoading(false) }
  }, [])

  useEffect(() => { fetchWorklist() }, [fetchWorklist])

  const goto = useCallback((next: StudioView, params?: GotoParams & { section?: string }) => {
    const p = new URLSearchParams()
    p.set('view', next)
    if (params?.state) p.set('state', params.state)
    if (params?.city) p.set('city', params.city)
    if (params?.industry) p.set('industry', params.industry)
    if (params?.section) p.set('section', params.section)
    setSearchParams(p)
  }, [setSearchParams])

  const gotoUncodified = useCallback((items: UncodifiedItem[]) => {
    setSeedUncodified(items)
    goto('pipeline', { section: 'review' })
  }, [goto])

  const meters = worklist?.meters
  const codifiedPct = meters && meters.requirements > 0
    ? Math.round((meters.codified / meters.requirements) * 100) : null

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col overflow-hidden rounded-xl border border-white/[0.06] bg-black">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <Sparkles className="h-4 w-4 text-emerald-400" /> Compliance Studio
        </h1>
        <div className="flex items-center gap-4">
          {/* The two meters — everything in this studio serves one of these. */}
          <div className="hidden items-center gap-4 font-mono text-[11px] uppercase tracking-wide text-zinc-500 sm:flex">
            <span className="text-emerald-400"
                  title={`Live requirements carrying a verified statute citation — what makes the data AUTHORITATIVE.${
                    meters && meters.keyless > 0
                      ? ` ${meters.keyless} row${meters.keyless === 1 ? '' : 's'} have no regulation key and can't codify until keyed.`
                      : ''
                  }`}>
              Authoritative <b className="text-emerald-300">{meters?.codified ?? '—'}</b>
              <span className="text-emerald-400/50">/{meters?.requirements ?? '—'}</span>
              {codifiedPct !== null && <span className="text-emerald-400/50"> ({codifiedPct}%)</span>}
              {meters && meters.keyless > 0 && (
                <span className="ml-1 text-amber-400/70" title={`${meters.keyless} uncodifiable — no regulation key`}>
                  ⚠{meters.keyless}
                </span>
              )}
            </span>
            <span className={meters && meters.open_items > 0 ? 'text-amber-400' : ''}
                  title="Total open worklist items across both funnels">
              Open <b>{meters?.open_items ?? '—'}</b>
            </span>
          </div>
          <button type="button" onClick={() => setAssistantOpen((v) => !v)}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${
              assistantOpen ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300' : 'border-white/[0.08] text-zinc-400 hover:border-white/20'
            }`}>
            <MessageCircle className="h-3.5 w-3.5" /> Guide
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap items-center gap-1 border-b border-white/[0.06] px-2 py-1.5">
        {TABS.map((t) => {
          const Icon = t.icon
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => goto(t.id)}
              className={`inline-flex items-center gap-1.5 rounded px-2 py-1 font-mono text-[10px] uppercase tracking-wide transition-colors ${
                view === t.id ? 'bg-white/[0.06] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              <Icon className="h-3 w-3" /> {t.label}
            </button>
          )
        })}
      </div>

      {/* Body: view router + optional assistant side panel */}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {view === 'home' && (
            <CommandCenter
              worklist={worklist}
              loading={worklistLoading}
              onRefresh={fetchWorklist}
              goto={goto}
              gotoUncodified={gotoUncodified}
            />
          )}
          {view === 'pipeline' && (
            <PipelineTab
              initialSection={searchParams.get('section')}
              initialUncodifiedItems={seedUncodified ?? undefined}
            />
          )}
          {view === 'coverage' && (
            <CoverageTab
              initialIndustry={searchParams.get('industry')}
              initialState={searchParams.get('state')}
              initialCity={searchParams.get('city')}
              initialHeadcount={searchParams.get('headcount')}
              onMutate={fetchWorklist}
              goto={goto}
            />
          )}
          {view === 'authority' && <AuthorityTab onMutate={fetchWorklist} />}
          {view === 'library' && (
            <LibraryTab
              initialState={searchParams.get('state')}
              initialCity={searchParams.get('city')}
              initialIndustry={searchParams.get('industry')}
              goto={goto}
            />
          )}
        </div>

        {assistantOpen && (
          <div className="w-80 shrink-0 border-l border-white/[0.06]">
            <StudioAssistant worklist={worklist} onClose={() => setAssistantOpen(false)} goto={goto} />
          </div>
        )}
      </div>
    </div>
  )
}
