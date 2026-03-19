import { useEffect, useState, useCallback, useMemo } from 'react'
import { api } from '../../api/client'
import { Button, Input, Textarea } from '../ui'
import {
  CATEGORY_LABELS,
} from '../../generated/complianceCategories'
import type { PreemptionRule, IndustryProfile, SpecialtyFilter } from './jurisdiction/types'
import { matchesSpecialty, matchesProfileRateTypes } from './jurisdiction/utils'
import SpecialtyFilterSelect from './jurisdiction/SpecialtyFilterSelect'

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
  previous_value: string | null
  last_verified_at: string | null
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

type ViewMode = 'requirements' | 'hierarchy' | 'legislation'

type Props = {
  id: string
  city: string
  state: string
  categoriesMissing?: string[]
  preemptionRules?: PreemptionRule[]
  selectedProfile?: IndustryProfile | null
  onCheckComplete?: () => void
  onNavigate?: (id: string) => void
}

const LEVEL_ORDER = ['federal', 'state', 'county', 'city']
const LEVEL_COLORS: Record<string, string> = {
  federal: 'text-zinc-400 bg-zinc-500/10',
  state: 'text-amber-400 bg-amber-500/10',
  county: 'text-purple-400 bg-purple-500/10',
  city: 'text-blue-400 bg-blue-500/10',
}

function getCategoryLabel(cat: string) {
  return CATEGORY_LABELS[cat] ?? cat
}


// ── Component ──────────────────────────────────────────────────────────────────

export default function JurisdictionDetailPanel({ id, city, state, categoriesMissing, preemptionRules, selectedProfile, onCheckComplete, onNavigate }: Props) {
  const [detail, setDetail] = useState<JurisdictionDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [specialtyRunning, setSpecialtyRunning] = useState(false)
  const [medicalRunning, setMedicalRunning] = useState(false)
  const [fedSourcesRunning, setFedSourcesRunning] = useState(false)
  const [fedPreview, setFedPreview] = useState<{ results: any[]; by_category: Record<string, any[]>; total: number } | null>(null)
  const [fedApplying, setFedApplying] = useState(false)
  const [scanMessages, setScanMessages] = useState<string[]>([])
  const [viewMode, setViewMode] = useState<ViewMode>('requirements')
  const [specialtyFilter, setSpecialtyFilter] = useState<SpecialtyFilter>('all')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState({ title: '', description: '', current_value: '', effective_date: '', source_url: '', source_name: '' })
  const [saving, setSaving] = useState(false)
  const [reordering, setReordering] = useState(false)

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

  function startSpecialtyCheck() {
    setSpecialtyRunning(true); setScanMessages([])
    const token = localStorage.getItem('matcha_access_token')
    const base = import.meta.env.VITE_API_URL || '/api'
    fetch(`${base}/admin/jurisdictions/${id}/check-specialty`, {
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
          if (data === '[DONE]') { setSpecialtyRunning(false); fetchDetail(); onCheckComplete?.(); return }
          try {
            const ev = JSON.parse(data)
            if (ev.type === 'error') { setScanMessages((p) => [...p, `Error: ${ev.message}`]); setSpecialtyRunning(false); return }
            if (ev.message) setScanMessages((p) => [...p, ev.message])
          } catch {}
        }
      }
      setSpecialtyRunning(false)
    }).catch(() => setSpecialtyRunning(false))
  }

  function startMedicalCheck() {
    setMedicalRunning(true); setScanMessages([])
    const token = localStorage.getItem('matcha_access_token')
    const base = import.meta.env.VITE_API_URL || '/api'
    fetch(`${base}/admin/jurisdictions/${id}/check-medical-compliance`, {
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
          if (data === '[DONE]') { setMedicalRunning(false); fetchDetail(); onCheckComplete?.(); return }
          try {
            const ev = JSON.parse(data)
            if (ev.type === 'error') { setScanMessages((p) => [...p, `Error: ${ev.message}`]); setMedicalRunning(false); return }
            if (ev.message) setScanMessages((p) => [...p, ev.message])
          } catch {}
        }
      }
      setMedicalRunning(false)
    }).catch(() => setMedicalRunning(false))
  }

  function startFedSourcesCheck() {
    setFedSourcesRunning(true); setScanMessages([]); setFedPreview(null)
    const token = localStorage.getItem('matcha_access_token')
    const base = import.meta.env.VITE_API_URL || '/api'
    fetch(`${base}/admin/jurisdictions/${id}/check-federal-sources`, {
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
          if (data === '[DONE]') { setFedSourcesRunning(false); return }
          try {
            const ev = JSON.parse(data)
            if (ev.type === 'error') { setScanMessages((p) => [...p, `Error: ${ev.message}`]); setFedSourcesRunning(false); return }
            if (ev.type === 'preview') {
              setFedPreview({ results: ev.results, by_category: ev.by_category, total: ev.total })
            }
            if (ev.message) setScanMessages((p) => [...p, ev.message])
          } catch {}
        }
      }
      setFedSourcesRunning(false)
    }).catch(() => setFedSourcesRunning(false))
  }

  async function applyFedSources() {
    if (!fedPreview) return
    setFedApplying(true)
    try {
      await api.post(`/admin/jurisdictions/${id}/apply-federal-sources`, { requirements: fedPreview.results })
      setFedPreview(null)
      fetchDetail()
      onCheckComplete?.()
    } catch { setScanMessages((p) => [...p, 'Error: Failed to apply federal sources']) }
    finally { setFedApplying(false) }
  }

  async function toggleBookmark(reqId: string) {
    if (!detail) return
    const res = await api.post<{ id: string; is_bookmarked: boolean }>(`/admin/jurisdictions/requirements/${reqId}/bookmark`, {})
    setDetail({ ...detail, requirements: detail.requirements.map((r) => r.id === res.id ? { ...r, is_bookmarked: res.is_bookmarked } : r) })
  }

  function startEditing(req: JurisdictionReq) {
    setEditingId(req.id)
    setEditForm({
      title: req.title || '', description: req.description || '',
      current_value: req.current_value || '',
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
      if (editForm.description !== (original.description || '')) changes.description = editForm.description
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

  async function reorderReq(reqId: string, direction: -1 | 1) {
    if (!detail || reordering) return
    const reqs = [...detail.requirements]
    const idx = reqs.findIndex((r) => r.id === reqId)
    if (idx < 0) return
    // Find neighbors in the same category
    const cat = reqs[idx].category
    const catReqs = reqs.filter((r) => r.category === cat)
    const catIdx = catReqs.findIndex((r) => r.id === reqId)
    const targetCatIdx = catIdx + direction
    if (targetCatIdx < 0 || targetCatIdx >= catReqs.length) return

    // Swap sort_order
    const a = catReqs[catIdx]
    const b = catReqs[targetCatIdx]
    const aOrder = a.sort_order ?? catIdx
    const bOrder = b.sort_order ?? targetCatIdx

    setReordering(true)
    try {
      await api.put('/admin/jurisdictions/requirements/reorder', {
        order: [
          { id: a.id, sort_order: bOrder },
          { id: b.id, sort_order: aOrder },
        ],
      })
      setDetail({
        ...detail,
        requirements: detail.requirements.map((r) => {
          if (r.id === a.id) return { ...r, sort_order: bOrder }
          if (r.id === b.id) return { ...r, sort_order: aOrder }
          return r
        }),
      })
    } finally { setReordering(false) }
  }

  // Filter requirements by specialty + profile
  const filteredReqs = useMemo(() => {
    if (!detail) return []
    let reqs = detail.requirements
    reqs = reqs.filter((r) => matchesSpecialty(r.category, specialtyFilter))
    if (selectedProfile) {
      const rateTypes = new Set(selectedProfile.rate_types)
      // Sort by profile's category_order
      const orderMap = new Map(selectedProfile.category_order.map((c, i) => [c, i]))
      reqs = [...reqs].sort((a, b) => {
        const oa = orderMap.get(a.category) ?? 999
        const ob = orderMap.get(b.category) ?? 999
        return oa - ob || (a.sort_order ?? 0) - (b.sort_order ?? 0)
      })
      // Mark non-focused but don't filter them out (they'll be de-emphasized in render)
      // Filter by rate_types if profile has them
      if (rateTypes.size > 0) {
        reqs = reqs.filter(r => matchesProfileRateTypes(r.requirement_key, rateTypes))
      }
    }
    return reqs
  }, [detail, specialtyFilter, selectedProfile])

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
    for (const cat of Object.keys(map)) {
      for (const level of Object.keys(map[cat])) {
        map[cat][level].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.title.localeCompare(b.title))
      }
    }
    return map
  }, [filteredReqs])

  // Build preemption lookup for this jurisdiction's state
  const preemptionLookup = useMemo(() => {
    if (!preemptionRules) return null
    const lookup: Record<string, { allows: boolean; notes: string | null }> = {}
    for (const r of preemptionRules) {
      if (r.state === state) {
        lookup[r.category] = { allows: r.allows_local_override, notes: r.notes }
      }
    }
    return Object.keys(lookup).length > 0 ? lookup : null
  }, [preemptionRules, state])

  // Profile focused check
  const profileFocused = selectedProfile ? new Set(selectedProfile.focused_categories) : null
  const profileEvidence = selectedProfile?.category_evidence ?? null

  function renderReqRow(req: JurisdictionReq) {
    const isFocused = !profileFocused || profileFocused.has(req.category)
    const confidence = profileEvidence?.[req.category]?.confidence

    if (editingId === req.id) {
      return (
        <div key={req.id} className="px-4 py-3 border-t border-zinc-800/30 bg-zinc-900/50 space-y-2">
          <Input label="Title" value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} />
          <Textarea label="Description" value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} rows={2} placeholder="Optional description" />
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
      <div key={req.id} className={`group flex items-start gap-2 px-4 py-2 border-t border-zinc-800/30 ${!isFocused ? 'opacity-40' : ''}`}>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm text-zinc-200">{req.title}</p>
            {req.is_bookmarked && <span className="text-[10px] text-amber-400">★</span>}
            {confidence !== undefined && (
              <span className={`w-2 h-2 rounded-full shrink-0 ${
                confidence >= 0.8 ? 'bg-emerald-500' : confidence >= 0.5 ? 'bg-amber-400' : 'bg-red-400'
              }`} title={`Confidence: ${(confidence * 100).toFixed(0)}%`} />
            )}
          </div>
          {req.description && (
            <p className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2">{req.description}</p>
          )}
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${LEVEL_COLORS[req.jurisdiction_level] || 'text-zinc-400 bg-zinc-500/10'}`}>
              {req.jurisdiction_level}
            </span>
            {req.current_value && <span className="text-[11px] text-zinc-400">{req.current_value}</span>}
            {req.previous_value && <span className="text-[11px] text-zinc-600">Prev: {req.previous_value}</span>}
            {req.effective_date && <span className="text-[11px] text-zinc-600">eff. {req.effective_date}</span>}
            {req.last_verified_at && <span className="text-[11px] text-zinc-600">verified {new Date(req.last_verified_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })}</span>}
            {req.source_name && (
              req.source_url
                ? <a href={req.source_url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-zinc-600 hover:text-zinc-400 underline">{req.source_name}</a>
                : <span className="text-[11px] text-zinc-600">{req.source_name}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          {/* Reorder arrows */}
          <button type="button" onClick={() => reorderReq(req.id, -1)} disabled={reordering}
            className="text-[11px] text-zinc-600 hover:text-zinc-300 px-0.5 transition-colors" title="Move up">▲</button>
          <button type="button" onClick={() => reorderReq(req.id, 1)} disabled={reordering}
            className="text-[11px] text-zinc-600 hover:text-zinc-300 px-0.5 transition-colors" title="Move down">▼</button>
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
        <div className="flex items-center gap-1.5">
          <Button variant="secondary" size="sm" disabled={scanning || specialtyRunning || medicalRunning || fedSourcesRunning || loading} onClick={startCheck}>
            {scanning ? 'Scanning...' : 'Run Check'}
          </Button>
          <button onClick={startSpecialtyCheck} disabled={scanning || specialtyRunning || medicalRunning || fedSourcesRunning || loading}
            className="px-2.5 py-1.5 text-[11px] font-medium border rounded transition-colors
              text-purple-400 border-purple-500/40 hover:bg-purple-500/10 disabled:opacity-30"
            title="Research healthcare + oncology specialty policies">
            {specialtyRunning ? 'Running...' : 'Specialty'}
          </button>
          <button onClick={startMedicalCheck} disabled={scanning || specialtyRunning || medicalRunning || fedSourcesRunning || loading}
            className="px-2.5 py-1.5 text-[11px] font-medium border rounded transition-colors
              text-teal-400 border-teal-500/40 hover:bg-teal-500/10 disabled:opacity-30"
            title="Research health specs (17 categories)">
            {medicalRunning ? 'Running...' : 'Health Specs'}
          </button>
          <button onClick={startFedSourcesCheck} disabled={scanning || specialtyRunning || medicalRunning || fedSourcesRunning || loading}
            className="px-2.5 py-1.5 text-[11px] font-medium border rounded transition-colors
              text-amber-400 border-amber-500/40 hover:bg-amber-500/10 disabled:opacity-30"
            title="Fetch from Federal Register, CMS, Congress.gov">
            {fedSourcesRunning ? 'Fetching...' : 'Fed Sources'}
          </button>
        </div>
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
        <SpecialtyFilterSelect value={specialtyFilter} onChange={setSpecialtyFilter} />
      </div>

      {/* SSE scan log */}
      {(scanning || specialtyRunning || medicalRunning || fedSourcesRunning) && scanMessages.length > 0 && (
        <div className="border border-zinc-800 rounded-lg px-3 py-2.5 mb-3 max-h-28 overflow-y-auto">
          {scanMessages.map((msg, i) => <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>)}
        </div>
      )}

      {/* Federal Sources preview */}
      {fedPreview && (
        <div className="border border-amber-500/30 rounded-lg px-3 py-2.5 mb-3 bg-amber-500/5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-[11px] font-medium text-amber-400">
              {fedPreview.total} results from government APIs · {Object.keys(fedPreview.by_category).length} categories
            </p>
            <div className="flex gap-1.5">
              <button onClick={() => setFedPreview(null)}
                className="px-2 py-1 text-[11px] text-zinc-400 border border-zinc-700 rounded hover:bg-zinc-800 transition-colors">
                Dismiss
              </button>
              <button onClick={applyFedSources} disabled={fedApplying}
                className="px-2 py-1 text-[11px] font-medium text-amber-400 border border-amber-500/40 rounded hover:bg-amber-500/10 disabled:opacity-30 transition-colors">
                {fedApplying ? 'Applying...' : `Apply ${fedPreview.total}`}
              </button>
            </div>
          </div>
          <div className="max-h-64 overflow-y-auto space-y-2">
            {Object.entries(fedPreview.by_category).sort(([a], [b]) => a.localeCompare(b)).map(([cat, items]) => (
              <div key={cat}>
                <p className="text-[10px] font-medium text-zinc-300 uppercase tracking-wider mb-0.5">
                  {getCategoryLabel(cat)} <span className="text-zinc-600">({items.length})</span>
                </p>
                {items.map((item: any, i: number) => (
                  <div key={i} className="ml-2 mb-1">
                    <p className="text-[11px] text-zinc-300 leading-4">
                      {item.title}
                      {item.source_url && (
                        <a href={item.source_url} target="_blank" rel="noreferrer"
                          className="ml-1 text-amber-500/60 hover:text-amber-400 text-[10px]">↗</a>
                      )}
                    </p>
                    {item.description && (
                      <p className="text-[10px] text-zinc-600 leading-3.5 mt-0.5">{item.description}</p>
                    )}
                    <p className="text-[10px] text-zinc-600">
                      {item.source_name}{item.effective_date ? ` · ${item.effective_date}` : ''}
                    </p>
                  </div>
                ))}
              </div>
            ))}
          </div>
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
                    <div className="px-4 pt-3 pb-1 flex items-center gap-2">
                      <p className="text-xs uppercase tracking-wide text-zinc-400 font-medium">{getCategoryLabel(cat)}</p>
                      {/* Preemption badge */}
                      {preemptionLookup?.[cat] && (
                        <span
                          className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${
                            preemptionLookup[cat].allows
                              ? 'bg-emerald-500/15 text-emerald-400'
                              : 'bg-red-500/15 text-red-400'
                          }`}
                          title={preemptionLookup[cat].notes ?? undefined}
                        >
                          {preemptionLookup[cat].allows ? 'Local override OK' : 'State preempts'}
                        </span>
                      )}
                    </div>
                    {LEVEL_ORDER.map((level) => {
                      const levelLabel = level === 'state' ? `state (${state})`
                        : level === 'city' ? `city (${city})`
                        : level
                      if (!levels[level]?.length) {
                        return (
                          <div key={level} className="px-4 pt-2 pb-1.5">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wider font-medium ${LEVEL_COLORS[level] || 'text-zinc-400 bg-zinc-500/10'}`}>
                              {levelLabel}
                            </span>
                            <p className="text-[11px] text-zinc-600 mt-1 pl-1">No {level}-level rules</p>
                          </div>
                        )
                      }
                      return (
                        <div key={level}>
                          <div className="px-4 pt-2 pb-0.5">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wider font-medium ${LEVEL_COLORS[level] || 'text-zinc-400 bg-zinc-500/10'}`}>
                              {levelLabel}
                            </span>
                          </div>
                          {levels[level].map(renderReqRow)}
                        </div>
                      )
                    })}
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
