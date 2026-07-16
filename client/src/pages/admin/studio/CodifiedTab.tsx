import { useCallback, useEffect, useMemo, useState } from 'react'
import { BadgeCheck, ChevronDown, ChevronRight, ExternalLink, Landmark, MapPin } from 'lucide-react'
import { api } from '../../../api/client'
import { Button } from '../../../components/ui'
import { LABEL } from '../../../components/ui/typography'
import { buildCodifiedSchema } from './codifiedSchema'
import { fmtDate, libraryLink } from './utils'
import type {
  AuditResponse, AuditRow, AuthorityNode, BreakdownRow, CodifiedFunnel,
  CodifiedSelection, GotoParams, StudioView, UncodifiedItem,
} from './types'

type Props = {
  initialState?: string | null
  goto: (next: StudioView, params?: GotoParams & { section?: string }) => void
  gotoUncodified: (items: UncodifiedItem[]) => void
}

const PAGE = 50

const GROUP_LABELS: Record<string, string> = {
  labor: 'labor',
  healthcare: 'healthcare',
  medical_compliance: 'medical-compliance',
  life_sciences: 'life-sciences',
  supplementary: 'supplementary',
  other: 'uncategorized',
}

function groupNoun(group: string) {
  return GROUP_LABELS[group] || group.replace(/_/g, '-')
}

/** codified / total as a bar. Emerald because codified is the asset. */
function Meter({ codified, total, className = '' }: { codified: number; total: number; className?: string }) {
  const pct = total > 0 ? Math.round((codified / total) * 100) : 0
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <span className="h-1 w-16 shrink-0 overflow-hidden rounded-full bg-zinc-800">
        <span className="block h-full rounded-full bg-emerald-500" style={{ width: `${pct}%` }} />
      </span>
      <span className="w-14 shrink-0 text-right font-mono text-[11px] tabular-nums text-zinc-500">
        <b className={codified > 0 ? 'text-emerald-300' : 'text-zinc-600'}>{codified}</b>/{total}
      </span>
    </span>
  )
}

// The Codified library. Library (the geography tree) answers "which places do we
// cover"; this answers "what have we PROVEN, and of what body of law".
//
// The schema on the left is the whole point: a flat list of 1773 rows cannot say
// "there are 147 federal labor laws and 10 of them are codified", and that
// sentence — a named body of law, its denominator, and our share of it — is the
// only thing that tells an admin where to work next. Clicking any level of it
// filters the table; the table opens rows in place rather than bouncing to
// Library, because leaving the tab loses the schema you navigated by.
export default function CodifiedTab({ initialState, goto, gotoUncodified }: Props) {
  const [stage, setStage] = useState<'codified' | 'researched'>('codified')
  const [sel, setSel] = useState<CodifiedSelection | null>(null)
  const [page, setPage] = useState(0)
  const [openSections, setOpenSections] = useState<Set<string>>(
    () => new Set(initialState ? [initialState.toUpperCase()] : ['US']),
  )
  const [openNodes, setOpenNodes] = useState<Set<string>>(new Set())
  const [expandedRow, setExpandedRow] = useState<string | null>(null)

  const [breakdown, setBreakdown] = useState<BreakdownRow[] | null>(null)
  const [funnel, setFunnel] = useState<CodifiedFunnel | null>(null)
  const [audit, setAudit] = useState<AuditResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const selState = sel?.state || ''

  useEffect(() => {
    api.get<{ rows: BreakdownRow[] }>('/admin/studio/codified-breakdown')
      .then((r) => setBreakdown(r.rows))
      .catch(() => setBreakdown([]))
  }, [])

  const fetchFunnel = useCallback(async () => {
    const q = selState ? `?state=${selState}` : ''
    try { setFunnel(await api.get<CodifiedFunnel>(`/admin/studio/codified-funnel${q}`)) }
    catch { setFunnel(null) }
  }, [selState])

  const fetchAudit = useCallback(async () => {
    setLoading(true)
    const p = new URLSearchParams({
      citation: stage === 'codified' ? 'verified' : 'unverified',
      limit: String(PAGE),
      offset: String(page * PAGE),
    })
    if (sel?.jurisdictionId) p.set('jurisdiction_id', sel.jurisdictionId)
    if (sel?.category) p.set('category', sel.category)
    try { setAudit(await api.get<AuditResponse>(`/admin/jurisdictions/quality-audit?${p}`)) }
    catch { setAudit(null) }
    finally { setLoading(false) }
  }, [stage, sel, page])

  useEffect(() => { fetchFunnel() }, [fetchFunnel])
  useEffect(() => { fetchAudit() }, [fetchAudit])

  // Any filter change invalidates the cursor: page 7 of one selection is not
  // page 7 of another, and an out-of-range offset renders an empty table that
  // reads as "nothing here" rather than "wrong page".
  useEffect(() => { setPage(0); setExpandedRow(null) }, [stage, sel])

  const schema = useMemo(() => buildCodifiedSchema(breakdown ?? []), [breakdown])

  const rows = audit?.requirements ?? []
  const total = audit?.summary.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE))

  function toggle(set: Set<string>, key: string, apply: (s: Set<string>) => void) {
    const next = new Set(set)
    if (next.has(key)) next.delete(key); else next.add(key)
    apply(next)
  }

  function selectNode(node: AuthorityNode, group?: string, cat?: { category: string; name: string }) {
    setSel({
      jurisdictionId: node.id,
      state: node.state,
      label: node.label,
      group,
      category: cat?.category,
      categoryName: cat?.name,
    })
  }

  const isSelected = (node: AuthorityNode, group?: string, category?: string) =>
    sel?.jurisdictionId === node.id && sel?.group === group && sel?.category === category

  // Send the page into the Pipeline codify chain, clicked row first, so the
  // admin keeps working after the first one — the same modal the Command
  // Center seeds.
  function codifyFrom(row: AuditRow) {
    const codifiable = rows.filter((r) => r.regulation_key)
    const ordered = [row, ...codifiable.filter((r) => r.id !== row.id)]
    gotoUncodified(ordered.map((r): UncodifiedItem => ({
      id: r.id, title: r.title || '', regulation_key: r.regulation_key,
      description: r.description, current_value: r.current_value,
      source_url: r.source_url, source_name: null, state: r.state, city: r.city,
    })))
  }

  const tiles = funnel ? [
    {
      key: 'scoped', label: 'Scoped',
      value: funnel.scoped === null ? '—' : String(funnel.scoped.keyed + funnel.scoped.unkeyed),
      hint: funnel.scoped === null
        ? 'Pick a state — in-scope obligations resolve per jurisdiction chain.'
        : `${funnel.scoped.keyed} researchable · ${funnel.scoped.unkeyed} need a regulation key first. Labor-domain authority indexes only.`,
      tone: 'text-zinc-100',
    },
    {
      key: 'pending', label: 'Pending', value: String(funnel.pending),
      hint: 'Researched and staged, not approved — not live, not served.',
      tone: 'text-zinc-100',
      onClick: funnel.pending ? () => goto('pipeline', { section: 'review' }) : undefined,
    },
    {
      key: 'researched', label: 'Researched', value: String(funnel.researched),
      hint: 'Live in the catalog, but carrying no verified statute citation — hidden from businesses.',
      tone: 'text-amber-300', onClick: () => setStage('researched'),
    },
    {
      key: 'codified', label: 'Codified', value: String(funnel.codified),
      hint: 'Verified statute citation + backing authority item. The only rows a business is shown.',
      tone: 'text-emerald-300', onClick: () => setStage('codified'),
    },
  ] : []

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <BadgeCheck className="h-4 w-4 text-emerald-400" /> Codified
        </h1>
        <span className="font-mono text-[11px] text-zinc-600">
          Businesses are served codified rows only.
        </span>
      </div>

      {/* The funnel: left to right is the road a row travels to become the asset. */}
      <div className="mb-4 flex items-stretch gap-1">
        {tiles.map((t, i) => (
          <div key={t.key} className="flex flex-1 items-center gap-1">
            <div title={t.hint} onClick={t.onClick}
              className={`flex-1 rounded-lg border px-4 py-3 text-center transition-colors ${
                t.onClick ? 'cursor-pointer hover:border-white/20' : ''
              } ${
                (t.key === 'codified' && stage === 'codified') || (t.key === 'researched' && stage === 'researched')
                  ? 'border-white/20 bg-white/[0.04]' : 'border-zinc-800'
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

      <div className="grid grid-cols-5 gap-4">
        {/* ── The schema ── */}
        <div className="col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <h2 className={LABEL}>By authority</h2>
            {sel && (
              <button type="button" onClick={() => setSel(null)}
                className="text-[11px] text-zinc-500 hover:text-zinc-300">Clear</button>
            )}
          </div>
          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <div className="max-h-[60vh] divide-y divide-zinc-800/60 overflow-y-auto text-sm">
              {breakdown === null ? (
                <p className="px-3 py-6 text-sm text-zinc-500">Loading...</p>
              ) : schema.length === 0 ? (
                <p className="px-3 py-8 text-center text-sm text-zinc-600">Catalog is empty.</p>
              ) : schema.map((section) => {
                const open = openSections.has(section.code)
                return (
                  <div key={section.code}>
                    <div onClick={() => toggle(openSections, section.code, setOpenSections)}
                      className="flex cursor-pointer items-center gap-2 px-3 py-2 hover:bg-zinc-800/30">
                      {open ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
                            : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-zinc-500" />}
                      {section.code === 'US'
                        ? <Landmark className="h-3.5 w-3.5 shrink-0 text-zinc-500" />
                        : <MapPin className="h-3 w-3 shrink-0 text-amber-400/70" />}
                      <span className="flex-1 font-medium text-zinc-200">{section.label}</span>
                      <Meter codified={section.codified} total={section.total} />
                    </div>

                    {open && section.nodes.map((node) => {
                      const nodeOpen = openNodes.has(node.id)
                      return (
                        <div key={node.id} className="border-t border-zinc-800/60">
                          <div onClick={() => toggle(openNodes, node.id, setOpenNodes)}
                            className="flex cursor-pointer items-center gap-2 py-1.5 pl-8 pr-3 hover:bg-zinc-800/30">
                            {nodeOpen ? <ChevronDown className="h-3 w-3 shrink-0 text-zinc-600" />
                                      : <ChevronRight className="h-3 w-3 shrink-0 text-zinc-600" />}
                            <span className="flex-1 truncate text-zinc-300">{node.label}</span>
                            <span className="font-mono text-[10px] uppercase text-zinc-600">{node.level}</span>
                            <Meter codified={node.codified} total={node.total} />
                          </div>

                          {nodeOpen && node.groups.map((g) => {
                            const gKey = `${node.id}|${g.group}`
                            const gOpen = openNodes.has(gKey)
                            return (
                              <div key={gKey}>
                                {/* The sentence the whole tab exists to say. */}
                                <div
                                  onClick={() => { selectNode(node, g.group); toggle(openNodes, gKey, setOpenNodes) }}
                                  className={`flex cursor-pointer items-center gap-2 py-1.5 pl-14 pr-3 hover:bg-zinc-800/30 ${
                                    isSelected(node, g.group, undefined) ? 'bg-emerald-500/[0.07]' : ''
                                  }`}>
                                  <span className="flex-1 truncate text-[13px] text-zinc-400">
                                    {g.total} {node.label === 'Federal' ? 'federal' : node.level} {groupNoun(g.group)} laws
                                  </span>
                                  <Meter codified={g.codified} total={g.total} />
                                </div>

                                {gOpen && g.categories.map((c) => (
                                  <div key={c.category}
                                    onClick={() => selectNode(node, g.group, c)}
                                    className={`flex cursor-pointer items-center gap-2 py-1 pl-20 pr-3 hover:bg-zinc-800/30 ${
                                      isSelected(node, g.group, c.category) ? 'bg-emerald-500/[0.07]' : ''
                                    }`}>
                                    <span className="flex-1 truncate text-[12px] text-zinc-500">{c.name}</span>
                                    <Meter codified={c.codified} total={c.total} />
                                  </div>
                                ))}
                              </div>
                            )
                          })}
                        </div>
                      )
                    })}
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* ── The rows ── */}
        <div className="col-span-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="inline-flex rounded-lg border border-zinc-800 p-0.5">
              {(['codified', 'researched'] as const).map((s) => (
                <button key={s} type="button" onClick={() => setStage(s)}
                  className={`rounded px-2.5 py-1 font-mono text-[10px] uppercase tracking-wide transition-colors ${
                    stage === s ? 'bg-white/[0.06] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
                  }`}>
                  {s === 'codified' ? 'Codified' : 'Not codified'}
                </button>
              ))}
            </div>
            <span className="font-mono text-[11px] text-zinc-600">
              {total} row{total === 1 ? '' : 's'}{pages > 1 ? ` · ${page + 1}/${pages}` : ''}
            </span>
          </div>

          <p className="mb-2 truncate text-[11px] text-zinc-500">
            {sel
              ? `${sel.label} · ${sel.group ? groupNoun(sel.group) : ''}${sel.categoryName ? ` · ${sel.categoryName}` : ''}`
              : 'Whole catalog — pick an authority to narrow.'}
          </p>

          <div className="overflow-hidden rounded-lg border border-zinc-800">
            {loading ? (
              <p className="px-3 py-6 text-sm text-zinc-500">Loading...</p>
            ) : rows.length === 0 ? (
              <p className="px-3 py-8 text-center text-sm text-zinc-600">
                {stage === 'codified' ? 'Nothing codified here yet.' : 'Everything here is codified.'}
              </p>
            ) : (
              <div className="max-h-[60vh] divide-y divide-zinc-800/60 overflow-y-auto text-sm">
                {rows.map((r) => {
                  const open = expandedRow === r.id
                  return (
                    <div key={r.id}>
                      <div onClick={() => setExpandedRow(open ? null : r.id)}
                        className="group flex cursor-pointer items-center gap-2 px-3 py-2 hover:bg-zinc-800/30">
                        {open ? <ChevronDown className="h-3 w-3 shrink-0 text-zinc-600" />
                              : <ChevronRight className="h-3 w-3 shrink-0 text-zinc-600" />}
                        <span className="min-w-0 flex-1 truncate text-zinc-200" title={r.title || ''}>
                          {r.title || '(untitled)'}
                        </span>
                        <span className="w-40 shrink-0 truncate font-mono text-[11px] text-zinc-500"
                              title={(stage === 'codified' ? r.statute_citation : r.regulation_key) || ''}>
                          {stage === 'codified'
                            ? (r.statute_citation || '—')
                            : (r.regulation_key || <span className="text-amber-400/70">no key</span>)}
                        </span>
                        <span className="w-16 shrink-0 text-right text-[11px] text-zinc-600">
                          {stage === 'codified' ? fmtDate(r.citation_verified_at) : (r.city || r.state || '—')}
                        </span>
                      </div>

                      {/* In place — the payload already carries everything, and
                          leaving the tab would lose the schema you got here by. */}
                      {open && (
                        <div className="space-y-2 bg-zinc-900/40 px-3 py-3 pl-8">
                          {r.current_value && (
                            <p className="font-mono text-[12px] text-emerald-300">{r.current_value}</p>
                          )}
                          {r.description && (
                            <p className="text-[12px] leading-relaxed text-zinc-400">{r.description}</p>
                          )}
                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] text-zinc-600">
                            <span>{r.jurisdiction_name || r.state || '—'}</span>
                            <span>{r.category}</span>
                            {r.regulation_key && <span>{r.regulation_key}</span>}
                            {r.statute_citation && <span className="text-zinc-400">{r.statute_citation}</span>}
                            {r.citation_verified_at && <span>verified {fmtDate(r.citation_verified_at)}</span>}
                          </div>
                          <div className="flex items-center gap-3 pt-1">
                            {stage === 'researched' && r.regulation_key && (
                              <Button size="sm" variant="secondary" onClick={() => codifyFrom(r)}>Codify</Button>
                            )}
                            {r.source_url && (
                              <a href={r.source_url} target="_blank" rel="noreferrer"
                                 className="inline-flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300">
                                <ExternalLink className="h-3 w-3" /> Source
                              </a>
                            )}
                            <a href={libraryLink(r.state, r.city, undefined, r.id)}
                               className="text-[11px] text-zinc-500 hover:text-zinc-300">Open in Library →</a>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
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
      </div>
    </div>
  )
}
