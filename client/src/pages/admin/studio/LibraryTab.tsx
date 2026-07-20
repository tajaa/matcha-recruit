import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { ChevronDown, ChevronRight, Globe2, Landmark, MapPin } from 'lucide-react'
import { api } from '../../../api/client'
import { postSSE } from '../../../api/sse'
import { Button, Input, Modal } from '../../../components/ui'
import JurisdictionDetailPanel from '../../../components/admin/JurisdictionDetailPanel'
import { fmtDate } from './utils'
import type { GotoParams, ResearchItem, StudioView, TreeNode, TreeResponse } from './types'

type Props = {
  initialState?: string | null
  initialCity?: string | null
  initialIndustry?: string | null
  initialReq?: string | null
  goto: (next: StudioView, params?: GotoParams & { section?: string }) => void
}

// The REPOSITORY itself, as a GEOGRAPHY tree: federal pinned on top, then
// collapsible state groups carrying the statewide node + its counties/cities.
// This is the "shelf" — the raw registry, its housekeeping (add/delete/cleanup),
// and the baseline "needs research" worklist. Both funnels write into it.
export default function LibraryTab({ initialState, initialCity, initialIndustry, initialReq, goto }: Props) {
  const [tree, setTree] = useState<TreeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedMeta, setSelectedMeta] = useState<{ city: string; state: string } | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [addForm, setAddForm] = useState({ city: '', state: '', county: '' })
  const [saving, setSaving] = useState(false)
  const [cleaning, setCleaning] = useState(false)

  const [researchQueue, setResearchQueue] = useState<ResearchItem[]>([])
  const [loadingResearch, setLoadingResearch] = useState(false)
  const [researchingId, setResearchingId] = useState<string | null>(null)
  const [researchMessages, setResearchMessages] = useState<string[]>([])

  const [topMetroRunning, setTopMetroRunning] = useState(false)
  const [topMetroMessages, setTopMetroMessages] = useState<string[]>([])

  const fetchTree = useCallback(async () => {
    setLoading(true)
    try { setTree(await api.get<TreeResponse>('/admin/jurisdictions/tree')) }
    catch { setTree(null) }
    finally { setLoading(false) }
  }, [])

  const fetchResearchQueue = useCallback(async () => {
    setLoadingResearch(true)
    try { setResearchQueue(await api.get<ResearchItem[]>('/admin/research-queue')) }
    catch { setResearchQueue([]) }
    finally { setLoadingResearch(false) }
  }, [])

  useEffect(() => { fetchTree(); fetchResearchQueue() }, [fetchTree, fetchResearchQueue])

  // Resolve the URL coordinate (?state=&city=) to a node once the tree is loaded:
  // expand its state group and open its detail panel.
  useEffect(() => {
    if (!tree || !initialState) return
    const st = initialState.trim().toUpperCase()
    const wantCity = (initialCity || '').trim().toLowerCase()
    let node: TreeNode | null = null
    if (st === 'US' && !wantCity) {
      node = tree.federal[0] ?? null
    } else {
      const grp = tree.states.find((s) => s.code === st)
      if (grp) {
        if (!wantCity) node = grp.state_node
        else node = grp.children.find((c) => (c.city || '').toLowerCase() === wantCity) ?? null
      }
    }
    if (node) {
      setSelectedId(node.id)
      setSelectedMeta({ city: nodeLabel(node), state: node.state })
      setExpanded((prev) => new Set(prev).add(st))
    }
    // Only re-run when the URL coordinate or the tree identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tree, initialState, initialCity])

  // Header-safe label for a node (federal/state/county have no real city).
  const nodeLabel = (n: TreeNode) =>
    (n.city && !n.city.startsWith('_')) ? n.city : (n.display_name || n.state)

  function selectNode(node: TreeNode) {
    if (node.id === selectedId) { setSelectedId(null); setSelectedMeta(null); return }
    setSelectedId(node.id)
    setSelectedMeta({ city: node.city || node.display_name || node.state, state: node.state })
    // Keep the URL copy-pasteable (preserve any industry focus).
    goto('library', {
      state: node.state,
      city: node.city || undefined,
      industry: initialIndustry || undefined,
    })
  }

  function toggleGroup(code: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(code)) next.delete(code); else next.add(code)
      return next
    })
  }

  async function handleAdd(e: FormEvent) {
    e.preventDefault(); setSaving(true)
    try {
      await api.post('/admin/jurisdictions', {
        city: addForm.city.trim(), state: addForm.state.trim().toUpperCase(), county: addForm.county.trim() || null,
      })
      setAddForm({ city: '', state: '', county: '' }); setShowAddForm(false); fetchTree()
    } finally { setSaving(false) }
  }

  async function handleDelete(node: TreeNode) {
    const label = node.city || node.display_name || node.state
    if (!confirm(`Delete ${label}, ${node.state}? This removes all requirements and legislation.`)) return
    await api.delete(`/admin/jurisdictions/${node.id}`)
    if (selectedId === node.id) { setSelectedId(null); setSelectedMeta(null) }
    fetchTree()
  }

  async function handleCleanup() {
    if (!confirm('Run duplicate cleanup? This merges duplicate rows. Cannot be undone.')) return
    setCleaning(true)
    try { await api.post('/admin/jurisdictions/cleanup-duplicates', {}); fetchTree() }
    finally { setCleaning(false) }
  }

  function startResearch(item: ResearchItem) {
    setResearchingId(item.jurisdiction_id); setResearchMessages([])
    postSSE(
      `/admin/research-queue/${item.jurisdiction_id}/research`,
      undefined,
      (data) => {
        const ev = data as { type?: string; message?: string }
        if (ev.type === 'error') { setResearchMessages((p) => [...p, `Error: ${ev.message}`]); return true }
        const msg = ev.message
        if (msg) setResearchMessages((p) => [...p, msg])
      },
    )
      .then(() => { fetchResearchQueue(); fetchTree() })
      .catch(() => {})
      .finally(() => setResearchingId(null))
  }

  function handleRunTopMetros() {
    setTopMetroRunning(true); setTopMetroMessages([])
    postSSE(
      '/admin/jurisdictions/top-metros/check',
      undefined,
      (data) => {
        const ev = data as { type?: string; message?: string }
        if (ev.type === 'error') { setTopMetroMessages((p) => [...p, `Error: ${ev.message}`]); return true }
        const msg = ev.message
        if (msg) setTopMetroMessages((p) => [...p, msg])
      },
    )
      .then(() => fetchTree())
      .catch(() => {})
      .finally(() => setTopMetroRunning(false))
  }

  const totals = tree?.totals ?? null

  // Search filters nodes across the whole tree; matched groups auto-expand.
  const q = search.trim().toLowerCase()
  const filtered = useMemo(() => {
    if (!tree) return { federal: [] as TreeNode[], states: [] as TreeResponse['states'] }
    if (!q) return { federal: tree.federal, states: tree.states }
    const match = (n: TreeNode | null) => !!n && (
      (n.city || '').toLowerCase().includes(q) ||
      (n.display_name || '').toLowerCase().includes(q) ||
      n.state.toLowerCase().includes(q) ||
      (n.county || '').toLowerCase().includes(q)
    )
    const federal = tree.federal.filter(match)
    const states = tree.states
      .map((s) => {
        const stateHit = s.code.toLowerCase().includes(q) || match(s.state_node)
        const children = stateHit ? s.children : s.children.filter(match)
        if (!stateHit && children.length === 0) return null
        return { ...s, children }
      })
      .filter((s): s is TreeResponse['states'][number] => s !== null)
    return { federal, states }
  }, [tree, q])

  // Auto-expand groups that matched a search.
  useEffect(() => {
    if (!q) return
    setExpanded(new Set(filtered.states.map((s) => s.code)))
  }, [q, filtered.states])

  function nodeCounts(n: TreeNode) {
    return (
      <>
        <span className="text-right text-zinc-400 tabular-nums w-10">{n.requirement_count}</span>
        <span className="text-right text-zinc-500 tabular-nums w-8">{n.legislation_count}</span>
        <span className="text-right text-zinc-500 tabular-nums w-8">{n.location_count}</span>
        <span className="text-zinc-600 text-[11px] w-16 text-right">{fmtDate(n.last_verified_at)}</span>
      </>
    )
  }

  function renderNodeRow(n: TreeNode, opts: { indent?: boolean; icon?: ReactNode; label?: string; deletable?: boolean } = {}) {
    const label = opts.label ?? ((n.city && !n.city.startsWith('_')) ? n.city : (n.display_name || n.state))
    return (
      <div key={n.id}
        onClick={() => selectNode(n)}
        className={`group flex items-center gap-2 px-3 py-1.5 cursor-pointer transition-colors ${
          n.id === selectedId ? 'bg-zinc-800/60' : 'hover:bg-zinc-800/30'
        } ${opts.indent ? 'pl-9' : ''}`}>
        <div className="flex items-center gap-1.5 flex-1 min-w-0">
          {opts.icon}
          <span className="text-zinc-200 truncate">{label}</span>
          {n.county && !opts.label && <span className="text-[11px] text-zinc-600 shrink-0">{n.county} County</span>}
        </div>
        {!selectedId && nodeCounts(n)}
        {opts.deletable !== false && (
          <button type="button" onClick={(e) => { e.stopPropagation(); handleDelete(n) }}
            className="text-xs text-zinc-600 hover:text-red-400 px-1 opacity-0 group-hover:opacity-100 transition-all shrink-0">Delete</button>
        )}
      </div>
    )
  }

  const selectedJurisdiction = selectedMeta

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <Globe2 className="h-4 w-4 text-emerald-400" /> Library
        </h1>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" disabled={topMetroRunning} onClick={handleRunTopMetros}>
            {topMetroRunning ? 'Running Top 15...' : 'Run Top 15 Metros'}
          </Button>
          <Button variant="ghost" size="sm" disabled={cleaning} onClick={handleCleanup}>
            {cleaning ? 'Cleaning...' : 'Cleanup Duplicates'}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setShowAddForm(true)}>+ Add</Button>
        </div>
      </div>

      {topMetroRunning && topMetroMessages.length > 0 && (
        <div className="border border-zinc-800 rounded-lg px-3 py-2.5 mb-3 max-h-28 overflow-y-auto">
          {topMetroMessages.map((msg, i) => (
            <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>
          ))}
        </div>
      )}

      {totals && (
        <div className="grid grid-cols-4 gap-3 mb-4">
          {[
            { label: 'Places', value: totals.total_jurisdictions },
            { label: 'Requirements', value: totals.total_requirements },
            { label: 'Codified', value: totals.total_codified ?? 0 },
            { label: 'Legislation', value: totals.total_legislation },
          ].map((s) => (
            <div key={s.label} className="border border-zinc-800 rounded-lg px-4 py-3 text-center">
              <p className="text-xl font-semibold text-zinc-100">{s.value}</p>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>
      )}

      <div className="mb-3">
        <Input label="" placeholder="Search city, state, or county..." value={search}
          onChange={(e) => setSearch(e.target.value)} className="max-w-xs" />
      </div>

      <div className={selectedId ? 'grid grid-cols-5 gap-4' : ''}>
        <div className={selectedId ? 'col-span-2' : ''}>
          {loading ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : !tree || (filtered.federal.length === 0 && filtered.states.length === 0) ? (
            <p className="text-sm text-zinc-600">No jurisdictions found.</p>
          ) : (
            <div className="border border-zinc-800 rounded-lg overflow-hidden">
              {/* Column header (hidden in split view) */}
              {!selectedId && (
                <div className="flex items-center gap-2 px-3 py-2 bg-zinc-900/50 text-zinc-400 text-[11px] font-medium">
                  <span className="flex-1">Jurisdiction</span>
                  <span className="text-right w-10">Reqs</span>
                  <span className="text-right w-8">Leg.</span>
                  <span className="text-right w-8">Locs</span>
                  <span className="text-right w-16">Verified</span>
                  <span className="w-8" />
                </div>
              )}
              <div className="max-h-[65vh] overflow-y-auto divide-y divide-zinc-800/60 text-sm">
                {/* Federal — pinned on top */}
                {filtered.federal.map((n) =>
                  renderNodeRow(n, {
                    icon: <Landmark className="h-3.5 w-3.5 text-zinc-500 shrink-0" />,
                    label: n.display_name || 'Federal',
                    deletable: false,
                  })
                )}

                {/* State groups */}
                {filtered.states.map((grp) => {
                  const isOpen = expanded.has(grp.code)
                  const aggReq = (grp.state_node?.requirement_count ?? 0) +
                    grp.children.reduce((n, c) => n + c.requirement_count, 0)
                  return (
                    <div key={grp.code}>
                      <div
                        onClick={() => toggleGroup(grp.code)}
                        className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-zinc-800/30 transition-colors">
                        {isOpen ? <ChevronDown className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
                          : <ChevronRight className="h-3.5 w-3.5 text-zinc-500 shrink-0" />}
                        <span className="font-medium text-zinc-200 flex-1">{grp.code || '— (no state)'}</span>
                        <span className="text-[11px] text-zinc-600">
                          {grp.children.length} {grp.children.length === 1 ? 'place' : 'places'}
                          {aggReq > 0 && ` · ${aggReq} reqs`}
                        </span>
                      </div>
                      {isOpen && (
                        <div>
                          {grp.state_node && renderNodeRow(grp.state_node, {
                            indent: true,
                            icon: <MapPin className="h-3 w-3 text-amber-400/70 shrink-0" />,
                            label: `Statewide (${grp.code})`,
                            deletable: false,
                          })}
                          {grp.children.map((c) => renderNodeRow(c, { indent: true }))}
                          {grp.children.length === 0 && !grp.state_node && (
                            <p className="pl-9 py-1.5 text-[11px] text-zinc-600">No places yet.</p>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>

        {selectedId && selectedJurisdiction && (
          <div className="col-span-3">
            <JurisdictionDetailPanel
              id={selectedId}
              city={selectedJurisdiction.city}
              state={selectedJurisdiction.state}
              initialIndustry={initialIndustry}
              initialReq={initialReq}
              onViewCoverage={() => goto('coverage', {
                state: selectedJurisdiction.state,
                city: selectedJurisdiction.city || undefined,
                industry: initialIndustry || undefined,
              })}
              onCheckComplete={fetchTree}
            />
          </div>
        )}
      </div>

      {/* ── Needs-research baseline worklist ── */}
      <div className="mt-6">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
            Baseline research {researchQueue.filter((r) => r.status === 'needs_research').length > 0 &&
              <span className="text-zinc-500">· {researchQueue.filter((r) => r.status === 'needs_research').length} need research</span>}
          </h2>
          <Button variant="ghost" size="sm" onClick={fetchResearchQueue}>Refresh</Button>
        </div>

        {researchingId && researchMessages.length > 0 && (
          <div className="border border-zinc-800 rounded-lg px-3 py-2.5 mb-3 max-h-28 overflow-y-auto">
            {researchMessages.map((msg, i) => (
              <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>
            ))}
          </div>
        )}

        {loadingResearch ? (
          <p className="text-sm text-zinc-500">Loading...</p>
        ) : researchQueue.length === 0 ? (
          <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
            <p className="text-sm text-zinc-600">Research queue is empty.</p>
          </div>
        ) : (
          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60 max-h-[50vh] overflow-y-auto">
            {researchQueue.map((item) => (
              <div key={item.jurisdiction_id} className="flex items-center gap-4 px-4 py-2.5">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-zinc-200">{item.city}, {item.state}</p>
                  <div className="flex items-center gap-3 mt-0.5">
                    <span className={`text-[11px] ${item.status === 'needs_research' ? 'text-amber-400/70' : 'text-zinc-500'}`}>
                      {item.status === 'needs_research' ? 'Needs research' : 'Researched'}
                    </span>
                    <span className="text-[11px] text-zinc-600">{item.repo_count} reqs</span>
                    <span className="text-[11px] text-zinc-600">{item.location_count} locs · {item.company_count} companies</span>
                  </div>
                </div>
                {item.status === 'needs_research' && (
                  <Button variant="secondary" size="sm"
                    disabled={researchingId !== null}
                    onClick={() => startResearch(item)}>
                    {researchingId === item.jurisdiction_id ? 'Researching...' : 'Research'}
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <Modal open={showAddForm} onClose={() => setShowAddForm(false)} title="Add Jurisdiction" width="sm">
        <form onSubmit={handleAdd} className="space-y-3">
          <Input id="j-city" label="City" required value={addForm.city}
            onChange={(e) => setAddForm({ ...addForm, city: e.target.value })} placeholder="e.g. San Francisco" />
          <Input id="j-state" label="State (2-letter)" required value={addForm.state} maxLength={2}
            onChange={(e) => setAddForm({ ...addForm, state: e.target.value.toUpperCase() })} placeholder="e.g. CA" />
          <Input id="j-county" label="County (optional)" value={addForm.county}
            onChange={(e) => setAddForm({ ...addForm, county: e.target.value })} placeholder="e.g. San Francisco" />
          <div className="pt-1">
            <Button type="submit" disabled={saving} size="sm">{saving ? 'Adding...' : 'Add Jurisdiction'}</Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
