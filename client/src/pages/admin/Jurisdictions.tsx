import { useEffect, useState, useCallback } from 'react'
import type { FormEvent } from 'react'
import { api } from '../../api/client'
import { Button, Input, Modal } from '../../components/ui'
import JurisdictionDetailPanel from '../../components/admin/JurisdictionDetailPanel'

// ── Types ──────────────────────────────────────────────────────────────────────

type Jurisdiction = {
  id: string
  city: string
  state: string
  county: string | null
  parent_id: string | null
  parent_city: string | null
  parent_state: string | null
  children_count: number
  requirement_count: number
  legislation_count: number
  location_count: number
  auto_check_count: number
  inherits_from_parent: boolean
  last_verified_at: string | null
  created_at: string | null
}

type ListResponse = {
  jurisdictions: Jurisdiction[]
  totals: {
    total_jurisdictions: number
    total_requirements: number
    total_legislation: number
  }
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function Jurisdictions() {
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

  const fetchJurisdictions = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get<ListResponse>('/admin/jurisdictions')
      setJurisdictions(res.jurisdictions)
      setTotals(res.totals)
    } catch { setJurisdictions([]) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchJurisdictions() }, [fetchJurisdictions])

  async function handleAdd(e: FormEvent) {
    e.preventDefault(); setSaving(true)
    try {
      await api.post('/admin/jurisdictions', {
        city: addForm.city.trim(),
        state: addForm.state.trim().toUpperCase(),
        county: addForm.county.trim() || null,
      })
      setAddForm({ city: '', state: '', county: '' })
      setShowAddForm(false)
      fetchJurisdictions()
    } finally { setSaving(false) }
  }

  async function handleDelete(id: string, city: string, state: string) {
    if (!confirm(`Delete ${city}, ${state}? This removes all requirements and legislation for this jurisdiction.`)) return
    await api.delete(`/admin/jurisdictions/${id}`)
    setJurisdictions((prev) => prev.filter((j) => j.id !== id))
    if (selectedId === id) setSelectedId(null)
  }

  async function handleCleanup() {
    if (!confirm('Run duplicate cleanup? This merges duplicate jurisdiction rows. Cannot be undone.')) return
    setCleaning(true)
    try { await api.post('/admin/jurisdictions/cleanup-duplicates', {}); fetchJurisdictions() }
    finally { setCleaning(false) }
  }

  // Unique states for filter
  const states = [...new Set(jurisdictions.map((j) => j.state))].sort()

  const filtered = jurisdictions.filter((j) => {
    const q = search.toLowerCase()
    const matchesSearch = !search || j.city.toLowerCase().includes(q) || j.state.toLowerCase().includes(q) || (j.county ?? '').toLowerCase().includes(q)
    const matchesState = !stateFilter || j.state === stateFilter
    return matchesSearch && matchesState
  })

  const selectedJurisdiction = jurisdictions.find((j) => j.id === selectedId) ?? null

  function fmtDate(d: string | null) {
    if (!d) return '—'
    return new Date(d).toLocaleDateString()
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">Jurisdictions</h1>
          <p className="mt-1 text-sm text-zinc-500">Manage the jurisdiction registry — add, research, and remove entries.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" disabled={cleaning} onClick={handleCleanup}>
            {cleaning ? 'Cleaning...' : 'Cleanup Duplicates'}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => setShowAddForm(true)}>
            + Add Jurisdiction
          </Button>
        </div>
      </div>

      {/* Totals */}
      {totals && (
        <div className="mt-4 grid grid-cols-3 gap-3">
          {[
            { label: 'Jurisdictions', value: totals.total_jurisdictions },
            { label: 'Requirements', value: totals.total_requirements },
            { label: 'Legislation', value: totals.total_legislation },
          ].map((s) => (
            <div key={s.label} className="border border-zinc-800 rounded-lg px-4 py-3 text-center">
              <p className="text-xl font-semibold text-zinc-100">{s.value}</p>
              <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="mt-4 flex items-center gap-3">
        <Input label="" placeholder="Search city, state, county..." value={search}
          onChange={(e) => setSearch(e.target.value)} className="max-w-xs" />
        <div className="flex gap-1">
          <Button variant={!stateFilter ? 'secondary' : 'ghost'} size="sm" onClick={() => setStateFilter('')}>All</Button>
          {states.map((s) => (
            <Button key={s} variant={stateFilter === s ? 'secondary' : 'ghost'} size="sm" onClick={() => setStateFilter(s)}>
              {s}
            </Button>
          ))}
        </div>
      </div>

      {/* Main layout: table + detail panel */}
      <div className={`mt-4 ${selectedId ? 'grid grid-cols-5 gap-4' : ''}`}>
        {/* Table */}
        <div className={selectedId ? 'col-span-2' : 'col-span-5'}>
          {loading ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-zinc-600">No jurisdictions found.</p>
          ) : (
            <div className="border border-zinc-800 rounded-lg overflow-hidden">
              <div className="max-h-[70vh] overflow-y-auto">
                <table className="w-full text-sm text-left">
                  <thead className="bg-zinc-900/50 text-zinc-400 sticky top-0">
                    <tr>
                      <th className="px-3 py-2.5 font-medium">City / State</th>
                      {!selectedId && <th className="px-3 py-2.5 font-medium text-right">Reqs</th>}
                      {!selectedId && <th className="px-3 py-2.5 font-medium text-right">Leg.</th>}
                      {!selectedId && <th className="px-3 py-2.5 font-medium text-right">Locs</th>}
                      {!selectedId && <th className="px-3 py-2.5 font-medium">Last Verified</th>}
                      <th className="px-3 py-2.5 font-medium text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {filtered.map((j) => {
                      const isSelected = j.id === selectedId
                      return (
                        <tr
                          key={j.id}
                          onClick={() => setSelectedId(j.id === selectedId ? null : j.id)}
                          className={`cursor-pointer transition-colors ${isSelected ? 'bg-zinc-800/60' : 'hover:bg-zinc-800/30'}`}
                        >
                          <td className="px-3 py-2.5">
                            <div className="flex items-center gap-1.5">
                              {j.inherits_from_parent && (
                                <span className="text-[10px] text-zinc-600" title="Inherits from parent">↑</span>
                              )}
                              <div>
                                <p className="text-zinc-200 font-medium">{j.city}, {j.state}</p>
                                {j.county && <p className="text-[11px] text-zinc-600">{j.county} County</p>}
                                {j.parent_city && (
                                  <p className="text-[11px] text-zinc-600">↳ {j.parent_city}, {j.parent_state}</p>
                                )}
                              </div>
                            </div>
                          </td>
                          {!selectedId && <td className="px-3 py-2.5 text-right text-zinc-400">{j.requirement_count}</td>}
                          {!selectedId && <td className="px-3 py-2.5 text-right text-zinc-400">{j.legislation_count}</td>}
                          {!selectedId && <td className="px-3 py-2.5 text-right text-zinc-400">{j.location_count}</td>}
                          {!selectedId && <td className="px-3 py-2.5 text-zinc-500 text-[11px]">{fmtDate(j.last_verified_at)}</td>}
                          <td className="px-3 py-2.5 text-right">
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); handleDelete(j.id, j.city, j.state) }}
                              className="text-xs text-zinc-600 hover:text-red-400 px-1.5 py-0.5 transition-colors"
                            >
                              Delete
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Detail panel */}
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

      {/* Add Jurisdiction modal */}
      <Modal open={showAddForm} onClose={() => setShowAddForm(false)} title="Add Jurisdiction" width="sm">
        <form onSubmit={handleAdd} className="space-y-3">
          <Input id="j-city" label="City" required value={addForm.city}
            onChange={(e) => setAddForm({ ...addForm, city: e.target.value })}
            placeholder="e.g. San Francisco" />
          <Input id="j-state" label="State (2-letter)" required value={addForm.state} maxLength={2}
            onChange={(e) => setAddForm({ ...addForm, state: e.target.value.toUpperCase() })}
            placeholder="e.g. CA" />
          <Input id="j-county" label="County (optional)" value={addForm.county}
            onChange={(e) => setAddForm({ ...addForm, county: e.target.value })}
            placeholder="e.g. San Francisco" />
          <div className="pt-1">
            <Button type="submit" disabled={saving} size="sm">{saving ? 'Adding...' : 'Add Jurisdiction'}</Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
