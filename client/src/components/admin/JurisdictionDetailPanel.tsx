import { useEffect, useState, useCallback, useMemo } from 'react'
import { api } from '../../api/client'
import { Button, Input } from '../ui'
import { categoryLabel } from '../../types/compliance'
import type { RequirementCategory } from '../../types/compliance'

// ── Types ──────────────────────────────────────────────────────────────────────

type JurisdictionReq = {
  id: string
  requirement_key: string
  category: string
  jurisdiction_level: string
  jurisdiction_name: string
  title: string
  description: string | null
  current_value: string | null
  source_url: string | null
  source_name: string | null
  effective_date: string | null
  is_bookmarked: boolean
  sort_order: number | null
}

type LinkedLocation = {
  id: string
  name: string | null
  city: string
  company_name: string
}

type ChildJurisdiction = {
  id: string
  city: string
  state: string
}

type JurisdictionDetail = {
  id: string
  city: string
  state: string
  county: string | null
  parent_id: string | null
  children: ChildJurisdiction[]
  requirements: JurisdictionReq[]
  legislation: { id: string; category: string; title: string; current_status: string; expected_effective_date: string | null; source_url: string | null }[]
  locations: LinkedLocation[]
}

type SpecialtyFilter = 'all' | 'general' | 'healthcare' | 'oncology'
type ViewMode = 'requirements' | 'hierarchy' | 'legislation'

type Props = {
  id: string
  city: string
  state: string
  categoriesMissing?: string[]
  onCheckComplete?: () => void
  onNavigate?: (id: string) => void
}

const HEALTHCARE_CATS = new Set([
  'hipaa_privacy', 'billing_integrity', 'clinical_safety', 'healthcare_workforce',
  'corporate_integrity', 'research_consent', 'state_licensing', 'emergency_preparedness',
])
const ONCOLOGY_CATS = new Set([
  'radiation_safety', 'chemotherapy_handling', 'tumor_registry',
  'oncology_clinical_trials', 'oncology_patient_rights',
])

const LEVEL_ORDER = ['federal', 'state', 'county', 'city']
const LEVEL_COLORS: Record<string, string> = {
  federal: 'text-zinc-400 bg-zinc-500/10',
  state: 'text-amber-400 bg-amber-500/10',
  county: 'text-purple-400 bg-purple-500/10',
  city: 'text-blue-400 bg-blue-500/10',
}

function getCategoryLabel(cat: string) {
  return categoryLabel[cat as RequirementCategory] ?? cat
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function JurisdictionDetailPanel({ id, city, state, categoriesMissing, onCheckComplete, onNavigate }: Props) {
  const [detail, setDetail] = useState<JurisdictionDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [scanMessages, setScanMessages] = useState<string[]>([])
  const [viewMode, setViewMode] = useState<ViewMode>('requirements')
  const [specialtyFilter, setSpecialtyFilter] = useState<SpecialtyFilter>('all')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState({ title: '', current_value: '', effective_date: '', source_url: '', source_name: '' })
  const [saving, setSaving] = useState(false)

  const fetchDetail = useCallback(async () => {
    setLoading(true); setDetail(null); setScanMessages([])
    try { setDetail(await api.get<JurisdictionDetail>(`/admin/jurisdictions/${id}`)) }
    catch { setDetail(null) }
    finally { setLoading(false) }
  }, [id])

  useEffect(() => { fetchDetail() }, [fetchDetail])

  function startCheck() {
    setScanning(true); setScanMessages([])
    const token = localStorage.getItem('matcha_access_token')
    const base = import.meta.env.VITE_API_URL || '/api'
    fetch(`${base}/admin/jurisdictions/${id}/check`, {
      method: 'POST', headers: { Authorization: `Bearer ${token}` },
    }).then(async (res) => {
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
          if (data === '[DONE]') { setScanning(false); fetchDetail(); onCheckComplete?.(); return }
          try {
            const ev = JSON.parse(data)
            if (ev.type === 'error') { setScanMessages((p) => [...p, `Error: ${ev.message}`]); setScanning(false); return }
            if (ev.message) setScanMessages((p) => [...p, ev.message])
          } catch {}
        }
      }
      setScanning(false)
    }).catch(() => setScanning(false))
  }

  async function toggleBookmark(reqId: string) {
    if (!detail) return
    const res = await api.post<{ id: string; is_bookmarked: boolean }>(`/admin/jurisdictions/requirements/${reqId}/bookmark`, {})
    setDetail({ ...detail, requirements: detail.requirements.map((r) => r.id === res.id ? { ...r, is_bookmarked: res.is_bookmarked } : r) })
  }

  function startEditing(req: JurisdictionReq) {
    setEditingId(req.id)
    setEditForm({
      title: req.title || '', current_value: req.current_value || '',
      effective_date: req.effective_date || '', source_url: req.source_url || '',
      source_name: req.source_name || '',
    })
  }

  async function saveEdit() {
    if (!editingId || !detail) return
    setSaving(true)
    try {
      const original = detail.requirements.find((r) => r.id === editingId)
      if (!original) return
      const changes: Record<string, string> = {}
      if (editForm.title !== (original.title || '')) changes.title = editForm.title
      if (editForm.current_value !== (original.current_value || '')) changes.current_value = editForm.current_value
      if (editForm.effective_date !== (original.effective_date || '')) changes.effective_date = editForm.effective_date
      if (editForm.source_url !== (original.source_url || '')) changes.source_url = editForm.source_url
      if (editForm.source_name !== (original.source_name || '')) changes.source_name = editForm.source_name
      if (Object.keys(changes).length === 0) { setEditingId(null); return }
      const updated = await api.patch<JurisdictionReq>(`/admin/jurisdictions/requirements/${editingId}`, changes)
      setDetail({ ...detail, requirements: detail.requirements.map((r) => r.id === updated.id ? updated : r) })
      setEditingId(null)
    } finally { setSaving(false) }
  }

  // Filter requirements by specialty
  const filteredReqs = useMemo(() => {
    if (!detail) return []
    let reqs = detail.requirements
    if (specialtyFilter === 'healthcare') reqs = reqs.filter((r) => HEALTHCARE_CATS.has(r.category) || ONCOLOGY_CATS.has(r.category))
    else if (specialtyFilter === 'oncology') reqs = reqs.filter((r) => ONCOLOGY_CATS.has(r.category))
    else if (specialtyFilter === 'general') reqs = reqs.filter((r) => !HEALTHCARE_CATS.has(r.category) && !ONCOLOGY_CATS.has(r.category))
    return reqs
  }, [detail, specialtyFilter])

  // Group by category
  const groupedByCategory = useMemo(() => {
    const map: Record<string, JurisdictionReq[]> = {}
    for (const r of filteredReqs) {
      const cat = r.category || 'other'
      if (!map[cat]) map[cat] = []
      map[cat].push(r)
    }
    return map
  }, [filteredReqs])

  // Hierarchy view: category → jurisdiction_level → requirements
  const hierarchyGrouped = useMemo(() => {
    const map: Record<string, Record<string, JurisdictionReq[]>> = {}
    for (const r of filteredReqs) {
      const cat = r.category || 'other'
      if (!map[cat]) map[cat] = {}
      const level = r.jurisdiction_level || 'unknown'
      if (!map[cat][level]) map[cat][level] = []
      map[cat][level].push(r)
    }
    // Sort within each level
    for (const cat of Object.keys(map)) {
      for (const level of Object.keys(map[cat])) {
        map[cat][level].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.title.localeCompare(b.title))
      }
    }
    return map
  }, [filteredReqs])

  function renderReqRow(req: JurisdictionReq) {
    if (editingId === req.id) {
      return (
        <div key={req.id} className="px-4 py-3 border-t border-zinc-800/30 bg-zinc-900/50 space-y-2">
          <Input label="Title" value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} />
          <div className="grid grid-cols-2 gap-2">
            <Input label="Current Value" value={editForm.current_value} onChange={(e) => setEditForm({ ...editForm, current_value: e.target.value })} />
            <Input label="Effective Date" value={editForm.effective_date} onChange={(e) => setEditForm({ ...editForm, effective_date: e.target.value })} placeholder="YYYY-MM-DD" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Input label="Source Name" value={editForm.source_name} onChange={(e) => setEditForm({ ...editForm, source_name: e.target.value })} />
            <Input label="Source URL" value={editForm.source_url} onChange={(e) => setEditForm({ ...editForm, source_url: e.target.value })} />
          </div>
          <div className="flex gap-2 pt-1">
            <Button size="sm" disabled={saving} onClick={saveEdit}>{saving ? 'Saving...' : 'Save'}</Button>
            <Button variant="ghost" size="sm" onClick={() => setEditingId(null)}>Cancel</Button>
          </div>
        </div>
      )
    }

    return (
      <div key={req.id} className="group flex items-start gap-2 px-4 py-2 border-t border-zinc-800/30">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm text-zinc-200">{req.title}</p>
            {req.is_bookmarked && <span className="text-[10px] text-amber-400">★</span>}
          </div>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${LEVEL_COLORS[req.jurisdiction_level] || 'text-zinc-400 bg-zinc-500/10'}`}>
              {req.jurisdiction_level}
            </span>
            {req.current_value && <span className="text-[11px] text-zinc-400">{req.current_value}</span>}
            {req.effective_date && <span className="text-[11px] text-zinc-600">eff. {req.effective_date}</span>}
            {req.source_name && (
              req.source_url
                ? <a href={req.source_url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-zinc-600 hover:text-zinc-400 underline">{req.source_name}</a>
                : <span className="text-[11px] text-zinc-600">{req.source_name}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <button type="button" onClick={() => toggleBookmark(req.id)}
            className="text-[11px] text-zinc-600 hover:text-amber-400 px-1.5 py-0.5 transition-colors">
            {req.is_bookmarked ? 'Unbookmark' : 'Bookmark'}
          </button>
          <button type="button" onClick={() => startEditing(req)}
            className="text-[11px] text-zinc-600 hover:text-zinc-300 px-1.5 py-0.5 transition-colors">
            Edit
          </button>
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-medium text-zinc-100">{city}, {state}</h2>
          {detail && (
            <p className="text-[11px] text-zinc-500 mt-0.5">
              {detail.requirements.length} requirements · {detail.legislation.length} legislation · {detail.locations.length} locations
              {detail.county && ` · ${detail.county} County`}
            </p>
          )}
        </div>
        <Button variant="secondary" size="sm" disabled={scanning || loading} onClick={startCheck}>
          {scanning ? 'Scanning...' : 'Run Check'}
        </Button>
      </div>

      {/* Metro group (parent/children) */}
      {detail && (detail.parent_id || detail.children.length > 0) && (
        <div className="mb-3 border border-zinc-800 rounded-lg px-3 py-2.5">
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-1.5">Metro Group</p>
          <div className="flex flex-wrap gap-1.5">
            {detail.parent_id && onNavigate && (
              <button type="button" onClick={() => onNavigate(detail.parent_id!)}
                className="text-[11px] text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded hover:bg-amber-500/20 transition-colors">
                Parent ↑
              </button>
            )}
            {detail.children.map((c) => (
              <button key={c.id} type="button" onClick={() => onNavigate?.(c.id)}
                className="text-[11px] text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded hover:bg-blue-500/20 transition-colors">
                {c.city}, {c.state}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Missing categories */}
      {categoriesMissing && categoriesMissing.length > 0 && (
        <div className="mb-3 border border-zinc-800 rounded-lg px-3 py-2.5">
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-1.5">Missing categories</p>
          <div className="flex flex-wrap gap-1.5">
            {categoriesMissing.map((cat) => (
              <span key={cat} className="text-[10px] text-red-400/70 bg-red-500/10 px-2 py-0.5 rounded">{getCategoryLabel(cat)}</span>
            ))}
          </div>
        </div>
      )}

      {/* View controls: mode tabs + specialty filter */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1">
          {([
            { id: 'requirements' as ViewMode, label: 'Requirements' },
            { id: 'hierarchy' as ViewMode, label: 'Hierarchy' },
            { id: 'legislation' as ViewMode, label: 'Legislation' },
          ]).map((v) => (
            <Button key={v.id} variant={viewMode === v.id ? 'secondary' : 'ghost'} size="sm" onClick={() => setViewMode(v.id)}>
              {v.label}
            </Button>
          ))}
        </div>
        <select value={specialtyFilter} onChange={(e) => setSpecialtyFilter(e.target.value as SpecialtyFilter)}
          className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5 focus:border-zinc-500">
          <option value="all">All Specialties</option>
          <option value="general">General Labor</option>
          <option value="healthcare">Healthcare</option>
          <option value="oncology">Oncology</option>
        </select>
      </div>

      {/* SSE scan log */}
      {scanning && scanMessages.length > 0 && (
        <div className="border border-zinc-800 rounded-lg px-3 py-2.5 mb-3 max-h-28 overflow-y-auto">
          {scanMessages.map((msg, i) => <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>)}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-zinc-500">Loading...</p>
      ) : !detail ? (
        <p className="text-sm text-zinc-600">Failed to load detail.</p>
      ) : (
        <>
          {/* ── Requirements view ── */}
          {viewMode === 'requirements' && (
            filteredReqs.length === 0 ? (
              <div className="border border-zinc-800 rounded-lg px-4 py-6 text-center">
                <p className="text-sm text-zinc-600">No requirements {specialtyFilter !== 'all' ? 'for this specialty' : '— run a check to populate'}.</p>
              </div>
            ) : (
              <div className="border border-zinc-800 rounded-lg max-h-[55vh] overflow-y-auto">
                {Object.entries(groupedByCategory).map(([cat, reqs], catIdx) => (
                  <div key={cat}>
                    {catIdx > 0 && <div className="border-t border-zinc-800/60" />}
                    <div className="px-4 pt-3 pb-1">
                      <p className="text-xs uppercase tracking-wide text-zinc-400">{getCategoryLabel(cat)}</p>
                    </div>
                    {reqs.map(renderReqRow)}
                  </div>
                ))}
              </div>
            )
          )}

          {/* ── Hierarchy view ── */}
          {viewMode === 'hierarchy' && (
            filteredReqs.length === 0 ? (
              <div className="border border-zinc-800 rounded-lg px-4 py-6 text-center">
                <p className="text-sm text-zinc-600">No requirements.</p>
              </div>
            ) : (
              <div className="border border-zinc-800 rounded-lg max-h-[55vh] overflow-y-auto">
                {Object.entries(hierarchyGrouped).map(([cat, levels], catIdx) => (
                  <div key={cat}>
                    {catIdx > 0 && <div className="border-t border-zinc-800/60" />}
                    <div className="px-4 pt-3 pb-1">
                      <p className="text-xs uppercase tracking-wide text-zinc-400 font-medium">{getCategoryLabel(cat)}</p>
                    </div>
                    {LEVEL_ORDER.filter((l) => levels[l]?.length > 0).map((level) => (
                      <div key={level}>
                        <div className="px-4 pt-2 pb-0.5">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wider font-medium ${LEVEL_COLORS[level] || 'text-zinc-400 bg-zinc-500/10'}`}>
                            {level}
                          </span>
                        </div>
                        {levels[level].map(renderReqRow)}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )
          )}

          {/* ── Legislation view ── */}
          {viewMode === 'legislation' && (
            detail.legislation.length === 0 ? (
              <div className="border border-zinc-800 rounded-lg px-4 py-6 text-center">
                <p className="text-sm text-zinc-600">No legislation tracked.</p>
              </div>
            ) : (
              <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60 max-h-[55vh] overflow-y-auto">
                {detail.legislation.map((leg) => (
                  <div key={leg.id} className="px-4 py-2.5">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm text-zinc-200">{leg.title}</p>
                      <span className={`text-[10px] shrink-0 px-1.5 py-0.5 rounded ${
                        leg.current_status === 'effective' ? 'text-emerald-400 bg-emerald-500/10'
                          : leg.current_status === 'effective_soon' ? 'text-red-400 bg-red-500/10'
                          : leg.current_status === 'signed' ? 'text-amber-400 bg-amber-500/10'
                          : 'text-zinc-400 bg-zinc-500/10'
                      }`}>
                        {leg.current_status?.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[11px] text-zinc-500">{getCategoryLabel(leg.category)}</span>
                      {leg.expected_effective_date && <span className="text-[11px] text-zinc-600">eff. {leg.expected_effective_date}</span>}
                      {leg.source_url && (
                        <a href={leg.source_url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-zinc-600 hover:text-zinc-400 underline">source</a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )
          )}

          {/* Linked locations */}
          {detail.locations.length > 0 && (
            <div className="mt-3">
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-1.5">Linked Business Locations</p>
              <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
                {detail.locations.map((loc) => (
                  <div key={loc.id} className="flex items-center justify-between px-3 py-2">
                    <p className="text-sm text-zinc-300">{loc.company_name}</p>
                    <p className="text-[11px] text-zinc-500">{loc.name || loc.city}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
