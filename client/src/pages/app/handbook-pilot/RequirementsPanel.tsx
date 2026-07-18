import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  CheckCircle2, ChevronDown, ChevronRight, Circle, Loader2, Scale, Wand2,
} from 'lucide-react'
import {
  getPilotHandbook,
  type AssembledHandbook, type ComplianceGap, type ComplianceScanResult, type CoverageEntry,
} from '../../../api/handbook-pilot/handbookPilot'
import { HelpHint } from '../../../components/ui/HelpHint'

// ---------------------------------------------------------------------------
// RequirementsPanel — the applicable jurisdiction requirements for this
// session's work locations, split into the ones a draft cites and the ones
// nothing cites yet. The uncited rows are the actionable half: [Draft] hands
// the requirement to the pilot as a targeted prompt.
//
// Two signals overlap here and they mean different things:
//   * cited / uncited — deterministic, free, recomputed after every turn. It
//     asks "does any draft cite this requirement's id?", NOT "is the company
//     compliant?". A requirement can be uncited and perfectly well covered by
//     an existing handbook, or simply out of this session's scope.
//   * gap severity     — from the on-demand Gemini compliance scan, which grades
//     the drafted *language* against each required topic. Overlaid onto the rows
//     when a scan has run.
// ---------------------------------------------------------------------------

export const SEVERITY_STYLE: Record<string, string> = {
  critical: 'bg-red-500/10 text-red-300 border-red-500/30',
  important: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
  recommended: 'bg-sky-500/10 text-sky-300 border-sky-500/30',
}

export const SEVERITY_RANK: Record<string, number> = { critical: 0, important: 1, recommended: 2 }

const severityRank = (s: string | undefined) => SEVERITY_RANK[s ?? ''] ?? 2

const COVERAGE_HINT =
  "Cited means at least one draft in this session cites the requirement's id. "
  + 'Uncited is not the same as non-compliant — it may already be covered by your '
  + 'existing handbook, or fall outside this session\'s goal. The count updates after '
  + 'every drafting turn, edit, and promote.'

type Row = CoverageEntry & { cited: boolean; gap: ComplianceGap | null }
type Filter = 'uncited' | 'cited' | 'all'

interface RequirementsPanelProps {
  sessionId: string
  /** Bumped by the page whenever drafts may have changed → refetch (self-fetch mode). */
  refreshKey: number | string
  /** Handbook mode passes the payload it already holds; Build mode omits it and we fetch. */
  handbook?: AssembledHandbook | null
  /** Gap-severity overlay. Only available after the user runs a compliance scan. */
  scan?: ComplianceScanResult | null
  onDraft: (req: CoverageEntry) => void
  /** Handbook mode only — scroll the document to the draft that cites a requirement. */
  onViewSection?: (draftId: string) => void
  /** Embedded in the Handbook-mode compliance rail: no border chrome, no height cap. */
  compact?: boolean
}

// Join a scan gap to a requirement row. `requirement_key` is the grader's stable
// key (the source category, which coverage entries now carry too); the title is
// Gemini's echo of the requirement and drifts in wording, so it's only a
// fallback. Normalizing both ways lets `meal_rest_breaks` meet `meal-rest-breaks`.
const norm = (s: string | null | undefined) =>
  (s ?? '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

const catKey = (state: string, category: string | null) => `cat:${state}|${norm(category)}`
const titleKey = (state: string, title: string) => `title:${state}|${norm(title)}`

export default function RequirementsPanel({
  sessionId, refreshKey, handbook: handbookProp, scan, onDraft, onViewSection, compact,
}: RequirementsPanelProps) {
  const selfFetch = handbookProp === undefined
  const [fetched, setFetched] = useState<AssembledHandbook | null>(null)
  const [loading, setLoading] = useState(selfFetch)
  const [error, setError] = useState(false)
  const [filter, setFilter] = useState<Filter>('uncited')
  const [closed, setClosed] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!selfFetch) return
    let cancelled = false
    ;(async () => {
      try {
        const hb = await getPilotHandbook(sessionId)
        if (cancelled) return
        setFetched(hb)
        setError(false)
      } catch {
        // Keep whatever we already showed — a failed refresh must never look
        // like "this company has no applicable requirements".
        if (!cancelled) setError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [selfFetch, sessionId, refreshKey])

  const handbook = selfFetch ? fetched : handbookProp

  // Draft id → title, so a cited row can name the section covering it.
  const draftTitles = useMemo(() => {
    const m = new Map<string, string>()
    for (const s of [...(handbook?.sections ?? []), ...(handbook?.policies ?? [])]) m.set(s.id, s.title)
    return m
  }, [handbook])

  // Index gaps under both keys. On collision keep the MOST SEVERE gap — two
  // same-titled requirements (a state and a city minimum wage) must not let a
  // `recommended` overwrite a `critical`. Unjoined gaps are not lost: they still
  // render in the scan's own GapCard list.
  const gaps = useMemo(() => {
    const m = new Map<string, ComplianceGap>()
    const put = (k: string, g: ComplianceGap) => {
      const prev = m.get(k)
      if (!prev || severityRank(g.severity) < severityRank(prev.severity)) m.set(k, g)
    }
    for (const g of scan?.gaps ?? []) {
      if (g.requirement_key) put(catKey(g.state, g.requirement_key), g)
      if (g.requirement_title) put(titleKey(g.state, g.requirement_title), g)
    }
    return m
  }, [scan])

  const rows = useMemo<Row[]>(() => {
    const cov = handbook?.coverage
    if (!cov) return []
    const mk = (e: CoverageEntry, cited: boolean): Row => ({
      ...e,
      cited,
      gap: gaps.get(catKey(e.state, e.category)) ?? gaps.get(titleKey(e.state, e.title)) ?? null,
    })
    return [...cov.covered.map((e) => mk(e, true)), ...cov.uncovered.map((e) => mk(e, false))]
  }, [handbook, gaps])

  const shown = useMemo(
    () => rows.filter((r) => (filter === 'all' ? true : filter === 'cited' ? r.cited : !r.cited)),
    [rows, filter],
  )

  // Group by state; within a state, unresolved + most severe first.
  const groups = useMemo(() => {
    const by = new Map<string, Row[]>()
    for (const r of shown) {
      const k = r.state || 'Other'
      const list = by.get(k)
      if (list) list.push(r)
      else by.set(k, [r])
    }
    const rank = (r: Row) => (r.gap ? severityRank(r.gap.severity) : r.cited ? 4 : 3)
    return [...by.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([state, list]) => [state, [...list].sort((a, b) => rank(a) - rank(b) || a.title.localeCompare(b.title))] as const)
  }, [shown])

  const toggleState = useCallback((s: string) => {
    setClosed((prev) => {
      const next = new Set(prev)
      next.has(s) ? next.delete(s) : next.add(s)
      return next
    })
  }, [])

  const summary = handbook?.summary
  const total = summary?.law_records ?? 0
  const covered = summary?.covered ?? 0
  const uncovered = summary?.uncovered ?? 0
  const pct = total > 0 ? Math.round((covered / total) * 100) : 0

  const shell = compact
    ? 'flex flex-col'
    : 'flex flex-col border border-zinc-800 rounded-xl bg-zinc-950/40 overflow-hidden'

  if (loading) {
    return (
      <div className={`${shell} items-center justify-center py-8`}>
        <Loader2 className="h-4 w-4 animate-spin text-emerald-500" />
      </div>
    )
  }

  return (
    <div className={shell}>
      <div className={`${compact ? 'pb-2' : 'px-3 py-2.5 border-b border-zinc-800'}`}>
        <div className="flex items-center gap-1.5">
          <Scale className="h-4 w-4 text-emerald-500 shrink-0" />
          <span className="text-sm font-semibold text-zinc-200">Requirements</span>
          <HelpHint text={COVERAGE_HINT} />
          <span className="ml-auto text-[11px] text-zinc-500 tabular-nums">
            {covered}/{total} cited
          </span>
        </div>
        {total > 0 && (
          <div
            className="mt-2 h-1.5 rounded-full bg-zinc-800 overflow-hidden"
            title={`${covered} of ${total} applicable requirements cited by this session's drafts`}
          >
            <div
              className={`h-full rounded-full transition-[width] ${uncovered > 0 ? 'bg-amber-500' : 'bg-emerald-500'}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
      </div>

      {/* A failed refresh keeps the last good list on screen — say so, rather
          than letting a transient 500 read as "you have no requirements". */}
      {error && handbook && (
        <p className="text-[11px] text-amber-400/80 px-3 pb-2">⚠ Couldn't refresh — showing the last loaded requirements.</p>
      )}

      {!handbook ? (
        <p className="text-[11px] text-amber-400/70 px-3 py-3">
          ⚠ Couldn't load requirements. Send a message or switch sessions to retry.
        </p>
      ) : total === 0 ? (
        <p className="text-[11px] text-amber-400/70 px-3 py-3">
          No jurisdiction requirements found for this session's work locations. Add employee
          work locations so applicable requirements can ground the drafts.
        </p>
      ) : (
        <>
          <div className={`flex items-center gap-1 ${compact ? 'pb-2' : 'px-2 py-2 border-b border-zinc-800'}`}>
            {([
              ['uncited', `Not cited (${uncovered})`],
              ['cited', `Cited (${covered})`],
              ['all', 'All'],
            ] as const).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setFilter(key)}
                className={`px-2 py-1 text-[11px] rounded-md ${
                  filter === key ? 'bg-zinc-800 text-emerald-400' : 'text-zinc-500 hover:text-zinc-300'}`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className={`${compact ? '' : 'max-h-[42vh]'} overflow-y-auto p-2 space-y-2`}>
            {shown.length === 0 && (
              <p className="text-[11px] text-zinc-600 px-1 py-2">
                {filter === 'uncited'
                  ? `All ${total} applicable requirements are cited by a draft.`
                  : 'Nothing here yet — ask the pilot to draft a section.'}
              </p>
            )}
            {groups.map(([state, list]) => {
              const open = !closed.has(state)
              const citedHere = list.filter((r) => r.cited).length
              return (
                <div key={state}>
                  <button
                    onClick={() => toggleState(state)}
                    className="w-full flex items-center gap-1.5 px-1 py-1 text-[11px] text-zinc-400 hover:text-zinc-200"
                  >
                    {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                    <span className="font-medium">{state}</span>
                    <span className="text-zinc-600 tabular-nums">
                      {filter === 'all' ? `${citedHere}/${list.length}` : list.length}
                    </span>
                  </button>
                  {open && (
                    <div className="space-y-1 pl-1">
                      {list.map((r) => (
                        <RequirementRow
                          key={r.cid}
                          row={r}
                          citedByTitle={r.cited_by.map((id) => draftTitles.get(id)).find(Boolean) ?? null}
                          onDraft={() => onDraft(r)}
                          onView={onViewSection && r.cited_by.length > 0
                            ? () => onViewSection(r.cited_by[0])
                            : undefined}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

function RequirementRow({ row, citedByTitle, onDraft, onView }: {
  row: Row
  citedByTitle: string | null
  onDraft: () => void
  onView?: () => void
}) {
  return (
    <div className={`rounded-lg border px-2.5 py-2 ${
      row.cited ? 'border-zinc-800 bg-zinc-900/40' : 'border-zinc-800/60 bg-zinc-900/20'}`}>
      <div className="flex items-start gap-1.5">
        {row.cited
          ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 mt-0.5 shrink-0" />
          : <Circle className="h-3.5 w-3.5 text-zinc-600 mt-0.5 shrink-0" />}
        <span className="text-[12px] text-zinc-200 flex-1 leading-snug">{row.title}</span>
        {row.gap && (
          <span
            className={`text-[9px] uppercase px-1 py-0.5 rounded border shrink-0 ${
              SEVERITY_STYLE[row.gap.severity] ?? SEVERITY_STYLE.recommended}`}
            title="Flagged by the compliance scan: the drafted language doesn't yet address this required topic"
          >
            {row.gap.severity}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2 mt-1 pl-5">
        <span className="text-[10px] text-zinc-600 truncate flex-1">
          {row.jurisdiction}
          {row.cited && citedByTitle ? ` · cited by ${citedByTitle}` : ''}
        </span>
        {row.cited ? (
          onView && (
            <button
              onClick={onView}
              title="Jump to the section that cites this requirement"
              className="shrink-0 text-[10px] text-zinc-500 hover:text-emerald-400"
            >
              View §
            </button>
          )
        ) : (
          <button
            onClick={onDraft}
            title="Ask the pilot to draft a section grounded in this requirement — drops a targeted prompt into the chat composer"
            className="shrink-0 inline-flex items-center gap-1 text-[10px] text-emerald-400 hover:text-emerald-300"
          >
            <Wand2 className="h-3 w-3" /> Draft
          </button>
        )}
      </div>
    </div>
  )
}
