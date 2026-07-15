import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Globe2 } from 'lucide-react'
import { api, authStreamHeaders } from '../../../api/client'
import { Button, Input, Modal } from '../../../components/ui'
import JurisdictionDetailPanel from '../../../components/admin/JurisdictionDetailPanel'
import { fmtDate } from './utils'
import type { Jurisdiction, ListResponse, ResearchItem } from './types'

// The REPOSITORY itself: the raw jurisdiction registry, its housekeeping
// (add/delete/cleanup), and the baseline "needs research" worklist. This is
// the library both funnels write into.
export default function LibraryTab() {
  const [jurisdictions, setJurisdictions] = useState<Jurisdiction[]>([])
  const [totals, setTotals] = useState<ListResponse['totals'] | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [stateFilter, setStateFilter] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
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

  const fetchJurisdictions = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get<ListResponse>('/admin/jurisdictions')
      setJurisdictions(res.jurisdictions); setTotals(res.totals)
    } catch { setJurisdictions([]) }
    finally { setLoading(false) }
  }, [])

  const fetchResearchQueue = useCallback(async () => {
    setLoadingResearch(true)
    try { setResearchQueue(await api.get<ResearchItem[]>('/admin/research-queue')) }
    catch { setResearchQueue([]) }
    finally { setLoadingResearch(false) }
  }, [])

  useEffect(() => { fetchJurisdictions(); fetchResearchQueue() }, [fetchJurisdictions, fetchResearchQueue])

  async function handleAdd(e: FormEvent) {
    e.preventDefault(); setSaving(true)
    try {
      await api.post('/admin/jurisdictions', {
        city: addForm.city.trim(), state: addForm.state.trim().toUpperCase(), county: addForm.county.trim() || null,
      })
      setAddForm({ city: '', state: '', county: '' }); setShowAddForm(false); fetchJurisdictions()
    } finally { setSaving(false) }
  }

  async function handleDelete(id: string, city: string, state: string) {
    if (!confirm(`Delete ${city}, ${state}? This removes all requirements and legislation.`)) return
    await api.delete(`/admin/jurisdictions/${id}`)
    setJurisdictions((prev) => prev.filter((j) => j.id !== id))
    if (selectedId === id) setSelectedId(null)
  }

  async function handleCleanup() {
    if (!confirm('Run duplicate cleanup? This merges duplicate rows. Cannot be undone.')) return
    setCleaning(true)
    try { await api.post('/admin/jurisdictions/cleanup-duplicates', {}); fetchJurisdictions() }
    finally { setCleaning(false) }
  }

  function startResearch(item: ResearchItem) {
    setResearchingId(item.jurisdiction_id); setResearchMessages([])
    const base = import.meta.env.VITE_API_URL || '/api'
    authStreamHeaders().then((headers) => fetch(`${base}/admin/research-queue/${item.jurisdiction_id}/research`, {
      method: 'POST', headers,
    })).then(async (res) => {
      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) return
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        for (const line of decoder.decode(value).split('\n')) {
          if (line.startsWith(': ')) continue
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6)
          if (data === '[DONE]') { setResearchingId(null); fetchResearchQueue(); return }
          try {
            const ev = JSON.parse(data)
            if (ev.type === 'error') { setResearchMessages((p) => [...p, `Error: ${ev.message}`]); setResearchingId(null); return }
            if (ev.message) setResearchMessages((p) => [...p, ev.message])
          } catch {}
        }
      }
      setResearchingId(null)
    }).catch(() => setResearchingId(null))
  }

  function handleRunTopMetros() {
    setTopMetroRunning(true); setTopMetroMessages([])
    const base = import.meta.env.VITE_API_URL || '/api'
    authStreamHeaders().then((headers) => fetch(`${base}/admin/jurisdictions/top-metros/check`, {
      method: 'POST', headers,
    })).then(async (res) => {
      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) return
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        for (const line of decoder.decode(value).split('\n')) {
          if (line.startsWith(': ')) continue
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6)
          if (data === '[DONE]') { setTopMetroRunning(false); fetchJurisdictions(); return }
          try {
            const ev = JSON.parse(data)
            if (ev.type === 'error') { setTopMetroMessages((p) => [...p, `Error: ${ev.message}`]); setTopMetroRunning(false); return }
            if (ev.message) setTopMetroMessages((p) => [...p, ev.message])
          } catch {}
        }
      }
      setTopMetroRunning(false)
    }).catch(() => setTopMetroRunning(false))
  }

  const states = [...new Set(jurisdictions.map((j) => j.state))].sort()
  const filtered = jurisdictions.filter((j) => {
    const q = search.toLowerCase()
    const matchesSearch = !search || j.city.toLowerCase().includes(q) || j.state.toLowerCase().includes(q)
    return matchesSearch && (!stateFilter || j.state === stateFilter)
  })
  const selectedJurisdiction = jurisdictions.find((j) => j.id === selectedId) ?? null
  const needsResearchCount = researchQueue.filter((r) => r.status === 'needs_research').length

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
            { label: 'Jurisdictions', value: totals.total_jurisdictions },
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

      <div className="flex items-center gap-3 mb-4">
        <Input label="" placeholder="Search city or state..." value={search}
          onChange={(e) => setSearch(e.target.value)} className="max-w-xs" />
        <div className="flex gap-1 overflow-x-auto">
          <Button variant={!stateFilter ? 'secondary' : 'ghost'} size="sm" onClick={() => setStateFilter('')}>All</Button>
          {states.map((s) => (
            <Button key={s} variant={stateFilter === s ? 'secondary' : 'ghost'} size="sm" onClick={() => setStateFilter(s)}>
              {s}
            </Button>
          ))}
        </div>
      </div>

      <div className={selectedId ? 'grid grid-cols-5 gap-4' : ''}>
        <div className={selectedId ? 'col-span-2' : ''}>
          {loading ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-zinc-600">No jurisdictions found.</p>
          ) : (
            <div className="border border-zinc-800 rounded-lg overflow-hidden">
              <div className="max-h-[65vh] overflow-y-auto">
                <table className="w-full text-sm text-left">
                  <thead className="bg-zinc-900/50 text-zinc-400 sticky top-0">
                    <tr>
                      <th className="px-3 py-2.5 font-medium">City / State</th>
                      {!selectedId && <th className="px-3 py-2.5 font-medium text-right">Reqs</th>}
                      {!selectedId && <th className="px-3 py-2.5 font-medium text-right">Leg.</th>}
                      {!selectedId && <th className="px-3 py-2.5 font-medium text-right">Locs</th>}
                      {!selectedId && <th className="px-3 py-2.5 font-medium">Verified</th>}
                      <th className="px-3 py-2.5 font-medium text-right" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {filtered.map((j) => (
                      <tr key={j.id}
                        onClick={() => setSelectedId(j.id === selectedId ? null : j.id)}
                        className={`cursor-pointer transition-colors ${j.id === selectedId ? 'bg-zinc-800/60' : 'hover:bg-zinc-800/30'}`}>
                        <td className="px-3 py-2.5">
                          <div className="flex items-center gap-1.5">
                            {j.inherits_from_parent && <span className="text-[10px] text-zinc-600" title="Inherits">↑</span>}
                            <div>
                              <p className="text-zinc-200 font-medium">{j.city}, {j.state}</p>
                              {j.county && <p className="text-[11px] text-zinc-600">{j.county} County</p>}
                              {j.parent_city && <p className="text-[11px] text-zinc-600">↳ {j.parent_city}, {j.parent_state}</p>}
                            </div>
                          </div>
                        </td>
                        {!selectedId && <td className="px-3 py-2.5 text-right text-zinc-400">{j.requirement_count}</td>}
                        {!selectedId && <td className="px-3 py-2.5 text-right text-zinc-400">{j.legislation_count}</td>}
                        {!selectedId && <td className="px-3 py-2.5 text-right text-zinc-400">{j.location_count}</td>}
                        {!selectedId && <td className="px-3 py-2.5 text-zinc-500 text-[11px]">{fmtDate(j.last_verified_at)}</td>}
                        <td className="px-3 py-2.5 text-right">
                          <button type="button" onClick={(e) => { e.stopPropagation(); handleDelete(j.id, j.city, j.state) }}
                            className="text-xs text-zinc-600 hover:text-red-400 px-1.5 py-0.5 transition-colors">Delete</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
              onCheckComplete={fetchJurisdictions}
            />
          </div>
        )}
      </div>

      {/* ── Needs-research baseline worklist ── */}
      <div className="mt-6">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
            Baseline research {needsResearchCount > 0 && <span className="text-zinc-500">· {needsResearchCount} need research</span>}
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
