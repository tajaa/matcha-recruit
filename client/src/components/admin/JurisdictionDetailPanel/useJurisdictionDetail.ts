import { useEffect, useState, useCallback, useMemo } from 'react'
import { api } from '../../../api/client'
import { postSSE } from '../../../api/sse'
import type { PreemptionRule, IndustryProfile } from '../jurisdiction/types'
import { matchesSpecialty, matchesProfileRateTypes } from '../jurisdiction/utils'
import type { SpecialtyFilter } from '../jurisdiction/types'
import type { JurisdictionDetail, JurisdictionReq, ViewMode, EditForm } from './types'
import { getCategoryLabel, reqAnchor, sectionAnchor } from './helpers'

type HookArgs = {
  id: string
  state: string
  preemptionRules?: PreemptionRule[]
  selectedProfile?: IndustryProfile | null
  onCheckComplete?: () => void
  initialIndustry?: string | null
  initialReq?: string | null
}

export function useJurisdictionDetail({ id, state, preemptionRules, selectedProfile, onCheckComplete, initialIndustry, initialReq }: HookArgs) {
  const [detail, setDetail] = useState<JurisdictionDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [specialtyRunning, setSpecialtyRunning] = useState(false)
  const [medicalRunning, setMedicalRunning] = useState(false)
  const [lifeSciRunning, setLifeSciRunning] = useState(false)
  const [fedSourcesRunning, setFedSourcesRunning] = useState(false)
  const [fedPreview, setFedPreview] = useState<{ results: any[]; by_category: Record<string, any[]>; total: number } | null>(null)
  const [fedApplying, setFedApplying] = useState(false)
  const [scanMessages, setScanMessages] = useState<string[]>([])
  const [viewMode, setViewMode] = useState<ViewMode>('requirements')
  const [specialtyFilter, setSpecialtyFilter] = useState<SpecialtyFilter>('all')
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<EditForm>({ title: '', description: '', current_value: '', effective_date: '', source_url: '', source_name: '' })
  const [saving, setSaving] = useState(false)
  const [reordering, setReordering] = useState(false)

  const fetchDetail = useCallback(async () => {
    setLoading(true); setDetail(null); setScanMessages([])
    try { setDetail(await api.get<JurisdictionDetail>(`/admin/jurisdictions/${id}`)) }
    catch { setDetail(null) }
    finally { setLoading(false) }
  }, [id])

  useEffect(() => { fetchDetail() }, [fetchDetail])

  // The five scans differ only by endpoint, which spinner they own, and whether
  // they refetch afterwards — so they share one driver rather than five copies
  // of the same stream plumbing.
  const runScan = useCallback((
    endpoint: string,
    setRunning: (v: boolean) => void,
    opts: { refetch?: boolean; onEvent?: (ev: any) => void } = {},
  ) => {
    setRunning(true); setScanMessages([])
    postSSE(
      `/admin/jurisdictions/${id}/${endpoint}`,
      undefined,
      (data) => {
        const ev = data as { type?: string; message?: string }
        if (ev.type === 'error') { setScanMessages((p) => [...p, `Error: ${ev.message}`]); return }
        opts.onEvent?.(ev)
        const msg = ev.message
        if (msg) setScanMessages((p) => [...p, msg])
      },
    )
      .then(() => {
        if (opts.refetch !== false) { fetchDetail(); onCheckComplete?.() }
      })
      .catch(() => {})
      .finally(() => setRunning(false))
  }, [id, fetchDetail, onCheckComplete])

  const startCheck = () => runScan('check', setScanning)
  const startSpecialtyCheck = () => runScan('check-specialty', setSpecialtyRunning)
  const startMedicalCheck = () => runScan('check-medical-compliance', setMedicalRunning)
  const startLifeSciCheck = () => runScan('check-life-sciences', setLifeSciRunning)

  function startFedSourcesCheck() {
    setFedPreview(null)
    runScan('check-federal-sources', setFedSourcesRunning, {
      refetch: false,
      onEvent: (ev) => {
        if (ev.type === 'preview') {
          setFedPreview({ results: ev.results, by_category: ev.by_category, total: ev.total })
        }
      },
    })
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

  // Available categories with counts
  const availableCategories = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const r of filteredReqs) {
      const cat = r.category || 'other'
      counts[cat] = (counts[cat] || 0) + 1
    }
    return Object.entries(counts)
      .map(([cat, count]) => ({ cat, count, label: getCategoryLabel(cat) }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }, [filteredReqs])

  // Apply category filter
  const categoryFilteredReqs = useMemo(() => {
    if (!categoryFilter) return filteredReqs
    return filteredReqs.filter(r => r.category === categoryFilter)
  }, [filteredReqs, categoryFilter])

  // Requirements view is split into two sections grounded on the row's actual
  // `applicable_industries` (empty = general employment law that every business
  // here answers to; tagged = industry-specific). Industry rows are sub-grouped
  // by tag, then category. A multi-tag row shows under each of its industries.
  const sectioned = useMemo(() => {
    const general: Record<string, JurisdictionReq[]> = {}
    const industries: Record<string, Record<string, JurisdictionReq[]>> = {}
    for (const r of categoryFilteredReqs) {
      const cat = r.category || 'other'
      const tags = r.applicable_industries ?? []
      if (tags.length === 0) {
        (general[cat] ??= []).push(r)
      } else {
        for (const tag of tags) {
          ((industries[tag] ??= {})[cat] ??= []).push(r)
        }
      }
    }
    const generalCount = Object.values(general).reduce((n, a) => n + a.length, 0)
    const industryTags = Object.keys(industries).sort((a, b) => a.localeCompare(b))
    return { general, generalCount, industries, industryTags }
  }, [categoryFilteredReqs])

  // Scroll the URL focus into view once detail + rows are present. A specific
  // requirement (initialReq) wins over a section (initialIndustry).
  useEffect(() => {
    if (loading || !detail) return
    const target = initialReq ? reqAnchor(initialReq)
      : initialIndustry ? (initialIndustry === 'general' ? sectionAnchor('general') : sectionAnchor(initialIndustry))
      : null
    if (!target) return
    // Defer so the section/row nodes are mounted.
    const t = window.setTimeout(() => {
      document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 80)
    return () => window.clearTimeout(t)
    // Focus once per load/coordinate — not on every category-filter change.
  }, [loading, detail, initialIndustry, initialReq])

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

  return {
    detail, loading,
    scanning, specialtyRunning, medicalRunning, lifeSciRunning, fedSourcesRunning,
    fedPreview, setFedPreview, fedApplying,
    scanMessages,
    viewMode, setViewMode,
    specialtyFilter, setSpecialtyFilter,
    categoryFilter, setCategoryFilter,
    editingId, setEditingId,
    editForm, setEditForm,
    saving, reordering,
    startCheck, startSpecialtyCheck, startMedicalCheck, startLifeSciCheck, startFedSourcesCheck,
    applyFedSources, toggleBookmark, startEditing, saveEdit, reorderReq,
    filteredReqs, availableCategories, categoryFilteredReqs, sectioned, hierarchyGrouped,
    preemptionLookup, profileFocused, profileEvidence,
  }
}
