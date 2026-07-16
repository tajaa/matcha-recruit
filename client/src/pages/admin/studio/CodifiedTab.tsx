import { useCallback, useEffect, useMemo, useState } from 'react'
import { BadgeCheck, ChevronRight, ExternalLink } from 'lucide-react'
import { api } from '../../../api/client'
import { Button, Input } from '../../../components/ui'
import { LABEL } from '../../../components/ui/typography'
import { fmtDate, libraryLink } from './utils'
import type { AuditResponse, AuditRow, CodifiedFunnel, StudioView, GotoParams, UncodifiedItem } from './types'

type Props = {
  initialState?: string | null
  goto: (next: StudioView, params?: GotoParams & { section?: string }) => void
  gotoUncodified: (items: UncodifiedItem[]) => void
}

const PAGE = 50

// A requirement is only worth something to a business if we can point at the
// statute it comes from. Library (the geography tree) answers "which places do
// we cover"; this answers "what have we actually PROVEN", and shows the pipeline
// that turns one into the other: scoped → pending → researched → codified.
//
// The table is the quality-audit endpoint filtered to one citation state, so the
// stage toggle is a server-side re-query, not a client filter — the corpus is
// ~1.8k rows and growing, and the old audit table's limit:2000-then-filter-in-JS
// is exactly what not to copy.
export default function CodifiedTab({ initialState, goto, gotoUncodified }: Props) {
  const [stage, setStage] = useState<'codified' | 'researched'>('codified')
  const [stateFilter, setStateFilter] = useState((initialState || '').toUpperCase())
  const [page, setPage] = useState(0)

  const [funnel, setFunnel] = useState<CodifiedFunnel | null>(null)
  const [audit, setAudit] = useState<AuditResponse | null>(null)
  const [loading, setLoading] = useState(true)

  // The state box is free text; only query on a real 2-letter code (or empty).
  const st = stateFilter.trim().toUpperCase()
  const stParam = st.length === 2 ? st : ''

  const fetchFunnel = useCallback(async () => {
    const q = stParam ? `?state=${stParam}` : ''
    try { setFunnel(await api.get<CodifiedFunnel>(`/admin/studio/codified-funnel${q}`)) }
    catch { setFunnel(null) }
  }, [stParam])

  const fetchAudit = useCallback(async () => {
    setLoading(true)
    const p = new URLSearchParams({
      citation: stage === 'codified' ? 'verified' : 'unverified',
      limit: String(PAGE),
      offset: String(page * PAGE),
    })
    if (stParam) p.set('state', stParam)
    try { setAudit(await api.get<AuditResponse>(`/admin/jurisdictions/quality-audit?${p}`)) }
    catch { setAudit(null) }
    finally { setLoading(false) }
  }, [stage, stParam, page])

  useEffect(() => { fetchFunnel() }, [fetchFunnel])
  useEffect(() => { fetchAudit() }, [fetchAudit])

  // A filter change invalidates the page cursor — page 7 of "codified in CA" is
  // not page 7 of "researched everywhere", and an out-of-range offset renders an
  // empty table that reads as "no data" rather than "wrong page".
  useEffect(() => { setPage(0) }, [stage, stParam])

  const rows = audit?.requirements ?? []
  const total = audit?.summary.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE))

  const codifiedPct = funnel && funnel.researched + funnel.codified > 0
    ? Math.round((funnel.codified / (funnel.researched + funnel.codified)) * 100)
    : null

  // Send the whole visible page into the Pipeline codify chain, clicked row
  // first, so the admin keeps working after the first one — same modal, same
  // next-row chain the Command Center seeds.
  function codifyFrom(row: AuditRow) {
    const codifiable = rows.filter((r) => r.regulation_key)
    const ordered = [row, ...codifiable.filter((r) => r.id !== row.id)]
    gotoUncodified(ordered.map((r): UncodifiedItem => ({
      id: r.id,
      title: r.title || '',
      regulation_key: r.regulation_key,
      description: r.description,
      current_value: r.current_value,
      source_url: r.source_url,
      source_name: null,
      state: r.state,
      city: r.city,
    })))
  }

  const tiles = useMemo(() => {
    if (!funnel) return []
    const scopedValue = funnel.scoped === null ? '—' : String(funnel.scoped.keyed + funnel.scoped.unkeyed)
    return [
      {
        key: 'scoped',
        label: 'Scoped',
        value: scopedValue,
        hint: funnel.scoped === null
          ? 'Pick a state — in-scope obligations are resolved per jurisdiction chain.'
          : `${funnel.scoped.keyed} researchable · ${funnel.scoped.unkeyed} need a regulation key first. Labor-domain authority indexes only.`,
        tone: 'text-zinc-100',
      },
      {
        key: 'pending',
        label: 'Pending',
        value: String(funnel.pending),
        hint: 'Researched and staged, not yet approved — not live, not served to tenants.',
        tone: 'text-zinc-100',
        onClick: funnel.pending ? () => goto('pipeline', { section: 'review' }) : undefined,
      },
      {
        key: 'researched',
        label: 'Researched',
        value: String(funnel.researched),
        hint: 'Live and served to tenants, but carrying no verified statute citation.',
        tone: 'text-amber-300',
        onClick: () => setStage('researched'),
      },
      {
        key: 'codified',
        label: 'Codified',
        value: String(funnel.codified),
        hint: 'Live with a verified statute citation and a backing authority item. The asset.',
        tone: 'text-emerald-300',
        onClick: () => setStage('codified'),
      },
    ]
  }, [funnel, goto])

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <BadgeCheck className="h-4 w-4 text-emerald-400" /> Codified
          {codifiedPct !== null && (
            <span className="font-mono text-[11px] font-normal text-zinc-500">
              {codifiedPct}% of live rows{stParam ? ` in ${stParam}` : ''}
            </span>
          )}
        </h1>
        <Input label="" placeholder="State (e.g. CA)" value={stateFilter} maxLength={2}
          onChange={(e) => setStateFilter(e.target.value.toUpperCase())} className="w-32" />
      </div>

      {/* Funnel — left to right is the road a row travels to become the asset. */}
      <div className="mb-4 flex items-stretch gap-1">
        {tiles.map((t, i) => (
          <div key={t.key} className="flex flex-1 items-center gap-1">
            <div
              title={t.hint}
              onClick={t.onClick}
              className={`flex-1 rounded-lg border px-4 py-3 text-center transition-colors ${
                t.onClick ? 'cursor-pointer hover:border-white/20' : ''
              } ${
                (t.key === 'codified' && stage === 'codified') || (t.key === 'researched' && stage === 'researched')
                  ? 'border-white/20 bg-white/[0.04]'
                  : 'border-zinc-800'
              }`}>
              <p className={`text-xl font-semibold tabular-nums ${t.tone}`}>{t.value}</p>
              <p className={`${LABEL} mt-0.5`}>{t.label}</p>
            </div>
            {i < tiles.length - 1 && <ChevronRight className="h-3.5 w-3.5 shrink-0 text-zinc-700" />}
          </div>
        ))}
      </div>

      {funnel && funnel.keyless > 0 && (
        <p className="mb-3 text-[11px] text-amber-400/70"
           title="codify_from_requirement joins on regulation_key — a keyless row 422s.">
          ⚠ {funnel.keyless} live row{funnel.keyless === 1 ? '' : 's'} carry no regulation key and cannot codify until keyed.
        </p>
      )}

      {/* Stage toggle — mirrors the two tiles above; also the table's server query. */}
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="inline-flex rounded-lg border border-zinc-800 p-0.5">
          {(['codified', 'researched'] as const).map((s) => (
            <button key={s} type="button" onClick={() => setStage(s)}
              className={`rounded px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide transition-colors ${
                stage === s ? 'bg-white/[0.06] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
              }`}>
              {s === 'codified' ? 'Codified' : 'Researched · uncited'}
            </button>
          ))}
        </div>
        <span className="font-mono text-[11px] text-zinc-600">
          {total} row{total === 1 ? '' : 's'}{pages > 1 ? ` · page ${page + 1}/${pages}` : ''}
        </span>
      </div>

      <div className="overflow-hidden rounded-lg border border-zinc-800">
        <div className="flex items-center gap-2 bg-zinc-900/50 px-3 py-2 text-[11px] font-medium text-zinc-400">
          <span className="flex-1">Requirement</span>
          <span className="w-24">Jurisdiction</span>
          <span className="w-32">Category</span>
          <span className="w-56">{stage === 'codified' ? 'Statute citation' : 'Regulation key'}</span>
          <span className="w-16 text-right">{stage === 'codified' ? 'Verified' : ''}</span>
          <span className="w-16" />
        </div>

        {loading ? (
          <p className="px-3 py-6 text-sm text-zinc-500">Loading...</p>
        ) : rows.length === 0 ? (
          <p className="px-3 py-8 text-center text-sm text-zinc-600">
            {stage === 'codified'
              ? `Nothing codified${stParam ? ` in ${stParam}` : ''} yet.`
              : `No uncited live rows${stParam ? ` in ${stParam}` : ''}.`}
          </p>
        ) : (
          <div className="max-h-[55vh] divide-y divide-zinc-800/60 overflow-y-auto text-sm">
            {rows.map((r) => (
              <div key={r.id} className="group flex items-center gap-2 px-3 py-2 hover:bg-zinc-800/30">
                <a href={libraryLink(r.state, r.city, undefined, r.id)}
                   className="min-w-0 flex-1 truncate text-zinc-200 hover:text-emerald-300"
                   title={r.title || ''}>
                  {r.title || '(untitled)'}
                </a>
                <span className="w-24 truncate text-[11px] text-zinc-500"
                      title={r.jurisdiction_name || ''}>
                  {r.city || r.state || r.jurisdiction_name || '—'}
                </span>
                <span className="w-32 truncate font-mono text-[11px] text-zinc-500">{r.category || '—'}</span>
                <span className="w-56 truncate font-mono text-[11px] text-zinc-400"
                      title={(stage === 'codified' ? r.statute_citation : r.regulation_key) || ''}>
                  {stage === 'codified'
                    ? (r.statute_citation || '—')
                    : (r.regulation_key || <span className="text-amber-400/70">no key</span>)}
                </span>
                <span className="w-16 text-right text-[11px] text-zinc-600">
                  {stage === 'codified' ? fmtDate(r.citation_verified_at) : ''}
                </span>
                <span className="flex w-16 justify-end">
                  {stage === 'researched' && r.regulation_key && (
                    <button type="button" onClick={() => codifyFrom(r)}
                      className="text-[11px] text-zinc-500 opacity-0 transition-all hover:text-emerald-300 group-hover:opacity-100">
                      Codify
                    </button>
                  )}
                  {stage === 'codified' && r.source_url && (
                    <a href={r.source_url} target="_blank" rel="noreferrer"
                       className="text-zinc-600 opacity-0 transition-all hover:text-zinc-300 group-hover:opacity-100">
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {pages > 1 && (
        <div className="mt-3 flex items-center justify-end gap-2">
          <Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Prev</Button>
          <Button variant="ghost" size="sm" disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      )}
    </div>
  )
}
