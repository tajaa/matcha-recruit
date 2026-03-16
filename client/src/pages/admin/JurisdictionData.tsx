import { useEffect, useState, useCallback, useMemo } from 'react'
import { api } from '../../api/client'
import { Button } from '../../components/ui'
import {
  CATEGORY_LABELS,
  CATEGORY_SHORT_LABELS,
  CATEGORY_GROUPS,
} from '../../generated/complianceCategories'
import JurisdictionDetailPanel from '../../components/admin/JurisdictionDetailPanel'
import ExplorerTab from '../../components/admin/jurisdiction/ExplorerTab'
import ProfileEditorModal from '../../components/admin/jurisdiction/ProfileEditorModal'
import { useIndustryProfiles } from '../../components/admin/jurisdiction/useIndustryProfiles'
import type { DataOverview, BookmarkedReq, FlatCity, CatCoverage } from '../../components/admin/jurisdiction/types'

// ── Types ──────────────────────────────────────────────────────────────────────

type Tab = 'explorer' | 'quality' | 'preemption' | 'bookmarks'
type SpecialtyFilter = 'all' | 'general' | 'healthcare' | 'oncology' | 'medical'

function getCategoryLabel(cat: string) {
  return CATEGORY_LABELS[cat] ?? cat
}

function getShortLabel(cat: string) {
  return CATEGORY_SHORT_LABELS[cat] ?? cat
}

function fmtDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
}

function matchesSpecialty(cat: string, filter: SpecialtyFilter): boolean {
  if (filter === 'all') return true
  const group = CATEGORY_GROUPS[cat]
  if (filter === 'healthcare') return group === 'healthcare' || group === 'oncology'
  if (filter === 'oncology') return group === 'oncology'
  if (filter === 'medical') return group === 'medical_compliance'
  // general = exclude healthcare, oncology, medical_compliance
  return group !== 'healthcare' && group !== 'oncology' && group !== 'medical_compliance'
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function JurisdictionData() {
  const [tab, setTab] = useState<Tab>('explorer')
  const [overview, setOverview] = useState<DataOverview | null>(null)
  const [loadingOverview, setLoadingOverview] = useState(true)
  const [selectedCityId, setSelectedCityId] = useState<string | null>(null)
  const [selectedCityMeta, setSelectedCityMeta] = useState<{ city: string; state: string; missing: string[] } | null>(null)
  const [bookmarks, setBookmarks] = useState<BookmarkedReq[]>([])
  const [loadingBookmarks, setLoadingBookmarks] = useState(false)
  const [specialtyFilter, setSpecialtyFilter] = useState<SpecialtyFilter>('all')
  const [hoveredCell, setHoveredCell] = useState<{ state: string; cat: string } | null>(null)
  const [metroScanning, setMetroScanning] = useState(false)
  const [metroMessages, setMetroMessages] = useState<string[]>([])
  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null)

  const { profiles, create: createProfile, update: updateProfile, remove: removeProfile } = useIndustryProfiles()
  const selectedProfile = profiles.find((p) => p.id === selectedProfileId) ?? null

  const fetchOverview = useCallback(async () => {
    setLoadingOverview(true)
    try { setOverview(await api.get<DataOverview>('/admin/jurisdictions/data-overview')) }
    catch { setOverview(null) }
    finally { setLoadingOverview(false) }
  }, [])

  const fetchBookmarks = useCallback(async () => {
    setLoadingBookmarks(true)
    try { setBookmarks(await api.get<BookmarkedReq[]>('/admin/jurisdictions/requirements/bookmarked')) }
    catch { setBookmarks([]) }
    finally { setLoadingBookmarks(false) }
  }, [])

  useEffect(() => { fetchOverview() }, [fetchOverview])
  useEffect(() => { if (tab === 'bookmarks') fetchBookmarks() }, [tab, fetchBookmarks])

  function openCity(flat: FlatCity) {
    setSelectedCityId(flat.id)
    setSelectedCityMeta({ city: flat.city, state: flat.stateName, missing: flat.categories_missing })
  }

  function startMetroCheck() {
    setMetroScanning(true); setMetroMessages([])
    const token = localStorage.getItem('matcha_access_token')
    const base = import.meta.env.VITE_API_URL || '/api'
    fetch(`${base}/admin/jurisdictions/top-metros/check`, {
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
          if (data === '[DONE]') { setMetroScanning(false); fetchOverview(); return }
          try {
            const ev = JSON.parse(data)
            if (ev.type === 'run_completed') { setMetroScanning(false); fetchOverview(); return }
            const msg = ev.message || (ev.city && `${ev.city}, ${ev.state}`) || null
            if (msg) setMetroMessages((p) => [...p, msg])
          } catch {}
        }
      }
      setMetroScanning(false)
    }).catch(() => setMetroScanning(false))
  }

  async function toggleBookmark(reqId: string) {
    await api.post(`/admin/jurisdictions/requirements/${reqId}/bookmark`, {})
    setBookmarks((prev) => prev.filter((b) => b.id !== reqId))
  }

  const sum = overview?.summary
  const allRequiredCats = sum?.required_categories ?? []
  const allStates = overview?.states ?? []

  // Filter categories by specialty
  const requiredCats = useMemo(() => {
    return allRequiredCats.filter((c) => matchesSpecialty(c, specialtyFilter))
  }, [allRequiredCats, specialtyFilter])

  // Flat city array for explorer
  const allCities = useMemo<FlatCity[]>(() => {
    const rows: FlatCity[] = []
    for (const st of allStates) {
      for (const city of st.cities) {
        const present = city.categories_present.filter((c) => matchesSpecialty(c, specialtyFilter))
        const missing = city.categories_missing.filter((c) => matchesSpecialty(c, specialtyFilter))
        const total = present.length + missing.length
        rows.push({
          ...city,
          stateName: st.state,
          coveragePct: total > 0 ? Math.round((present.length / total) * 100) : 0,
          gapCount: missing.length,
        })
      }
    }
    return rows
  }, [allStates, specialtyFilter])

  // Per-category coverage stats
  const categoryCoverage = useMemo<CatCoverage[]>(() => {
    const totalCities = allCities.length
    if (totalCities === 0) return []
    const counts: Record<string, number> = {}
    for (const city of allCities) {
      for (const cat of city.categories_present) {
        counts[cat] = (counts[cat] ?? 0) + 1
      }
    }
    return requiredCats.map((cat) => ({
      category: cat,
      label: getCategoryLabel(cat),
      shortLabel: getShortLabel(cat),
      count: counts[cat] ?? 0,
      total: totalCities,
      pct: Math.round(((counts[cat] ?? 0) / totalCities) * 100),
    }))
  }, [allCities, requiredCats])

  // Preemption matrix
  const preemptionMatrix = useMemo(() => {
    const matrix: Record<string, Record<string, { allows: boolean; notes: string | null }>> = {}
    const stateSet = new Set<string>()
    for (const r of overview?.preemption_rules ?? []) {
      stateSet.add(r.state)
      if (!matrix[r.state]) matrix[r.state] = {}
      matrix[r.state][r.category] = { allows: r.allows_local_override, notes: r.notes }
    }
    return { states: [...stateSet].sort(), matrix }
  }, [overview])

  const stateOptions = useMemo(() => [...new Set(allStates.map((s) => s.state))].sort(), [allStates])

  if (loadingOverview) return <p className="text-sm text-zinc-500">Loading...</p>
  if (!overview || !sum) return <p className="text-sm text-zinc-600">Failed to load data. Check that the server is running and you're logged in as admin.</p>

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">Jurisdiction Data</h1>
          <p className="mt-1 text-sm text-zinc-500">Compliance data repository overview</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Industry profile selector */}
          {profiles.length > 0 && (
            <select
              value={selectedProfileId ?? ''}
              onChange={(e) => setSelectedProfileId(e.target.value || null)}
              className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5"
            >
              <option value="">No Profile</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          )}
          <select value={specialtyFilter} onChange={(e) => setSpecialtyFilter(e.target.value as SpecialtyFilter)}
            className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5">
            <option value="all">All Specialties</option>
            <option value="general">General Labor</option>
            <option value="healthcare">Healthcare</option>
            <option value="oncology">Oncology</option>
            <option value="medical">Medical Compliance</option>
          </select>
          <button
            type="button"
            onClick={() => setProfileModalOpen(true)}
            className="text-zinc-500 hover:text-zinc-300 transition-colors p-1.5"
            title="Industry Profiles"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
          <Button variant="secondary" size="sm" disabled={metroScanning} onClick={startMetroCheck}>
            {metroScanning ? 'Running Top 15...' : 'Run Top 15 Metros'}
          </Button>
          <Button variant="ghost" size="sm" onClick={fetchOverview}>Refresh</Button>
        </div>
      </div>

      {/* Metro SSE progress */}
      {metroScanning && metroMessages.length > 0 && (
        <div className="mt-3 border border-zinc-800 rounded-lg px-3 py-2.5 max-h-28 overflow-y-auto">
          {metroMessages.map((msg, i) => (
            <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>
          ))}
        </div>
      )}

      {/* KPI Bar */}
      <div className="mt-4 grid grid-cols-5 gap-3">
        {[
          { label: 'States', value: `${sum.total_states}/50` },
          { label: 'Cities', value: sum.total_cities.toLocaleString() },
          { label: 'Coverage', value: `${sum.category_coverage_pct}%`, color: sum.category_coverage_pct >= 70 ? 'text-emerald-400' : sum.category_coverage_pct >= 40 ? 'text-amber-400' : 'text-red-400' },
          { label: 'Tier 1', value: `${sum.tier1_pct}%`, color: sum.tier1_pct >= 50 ? 'text-emerald-400' : sum.tier1_pct >= 20 ? 'text-amber-400' : 'text-red-400' },
          { label: 'Stale >90d', value: sum.stale_count.toString(), color: sum.stale_count === 0 ? 'text-emerald-400' : sum.stale_count <= 10 ? 'text-amber-400' : 'text-red-400' },
        ].map((s) => (
          <div key={s.label} className="border border-zinc-800 rounded-lg px-3 py-3">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">{s.label}</p>
            <p className={`text-2xl font-bold tracking-tight mt-0.5 ${'color' in s ? s.color : 'text-zinc-100'}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 mt-5 mb-5">
        {([
          { id: 'explorer' as Tab, label: 'Explorer' },
          { id: 'quality' as Tab, label: 'Data Quality' },
          { id: 'preemption' as Tab, label: 'Preemption' },
          { id: 'bookmarks' as Tab, label: 'Bookmarks' },
        ]).map((t) => (
          <Button key={t.id} variant={tab === t.id ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t.id)}>
            {t.label}
          </Button>
        ))}
      </div>

      {/* ── Explorer Tab ── */}
      {tab === 'explorer' && (
        <>
          <ExplorerTab
            allCities={allCities}
            categoryCoverage={categoryCoverage}
            stateOptions={stateOptions}
            onSelectCity={openCity}
            selectedCityId={selectedCityId}
          />
          {/* Detail panel — shown alongside explorer when city selected */}
          {selectedCityId && selectedCityMeta && (
            <div className="mt-4">
              <div className="flex items-center justify-between mb-2">
                <button type="button" onClick={() => { setSelectedCityId(null); setSelectedCityMeta(null) }}
                  className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">← Back to list</button>
              </div>
              <JurisdictionDetailPanel
                id={selectedCityId}
                city={selectedCityMeta.city}
                state={selectedCityMeta.state}
                categoriesMissing={selectedCityMeta.missing}
                preemptionRules={overview.preemption_rules}
                selectedProfile={selectedProfile}
                onCheckComplete={fetchOverview}
              />
            </div>
          )}
        </>
      )}

      {/* ── Data Quality Tab ── */}
      {tab === 'quality' && (
        <div className="space-y-5">
          <div>
            <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Tier Breakdown</h2>
            <div className="border border-zinc-800 rounded-lg p-4 space-y-3">
              {[
                { tier: 1, label: 'Tier 1 — Structured (government feeds)', count: sum.tier_breakdown[1] ?? 0, color: 'bg-emerald-500', textColor: 'text-emerald-400' },
                { tier: 2, label: 'Tier 2 — Repository (verified data)', count: sum.tier_breakdown[2] ?? 0, color: 'bg-amber-400', textColor: 'text-amber-400' },
                { tier: 3, label: 'Tier 3 — Gemini (AI research)', count: sum.tier_breakdown[3] ?? 0, color: 'bg-red-400', textColor: 'text-red-400' },
              ].map(({ tier, label, count, color, textColor }) => {
                const total = (sum.tier_breakdown[1] ?? 0) + (sum.tier_breakdown[2] ?? 0) + (sum.tier_breakdown[3] ?? 0)
                const pct = total > 0 ? Math.round((count / total) * 100) : 0
                return (
                  <div key={tier}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-zinc-300">{label}</span>
                      <span className={`text-sm font-mono font-bold ${textColor}`}>{count} ({pct}%)</span>
                    </div>
                    <div className="h-2 rounded-full bg-zinc-800 overflow-hidden">
                      <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div>
            <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Data Freshness</h2>
            <div className="grid grid-cols-4 gap-3">
              {[
                { label: '≤ 7 days', value: sum.freshness['7d'], color: 'text-emerald-400' },
                { label: '8–30 days', value: sum.freshness['30d'], color: 'text-zinc-100' },
                { label: '31–90 days', value: sum.freshness['90d'], color: 'text-amber-400' },
                { label: '> 90 days', value: sum.freshness['stale'], color: 'text-red-400' },
              ].map((f) => {
                const freshTotal = sum.freshness['7d'] + sum.freshness['30d'] + sum.freshness['90d'] + sum.freshness['stale']
                const pct = freshTotal > 0 ? Math.round((f.value / freshTotal) * 100) : 0
                return (
                  <div key={f.label} className="border border-zinc-800 rounded-lg px-3 py-3 text-center">
                    <p className={`text-2xl font-bold ${f.color}`}>{f.value.toLocaleString()}</p>
                    <p className="text-[10px] text-zinc-500 uppercase tracking-wider mt-0.5">{f.label}</p>
                    <p className="text-[10px] font-mono text-zinc-600">{pct}%</p>
                  </div>
                )
              })}
            </div>
          </div>

          {overview!.structured_sources.length > 0 && (
            <div>
              <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Structured Data Sources</h2>
              <div className="border border-zinc-800 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-zinc-900/50 text-zinc-400">
                    <tr>
                      <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Source</th>
                      <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Type</th>
                      <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Categories</th>
                      <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Records</th>
                      <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Last Fetch</th>
                      <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {overview!.structured_sources.map((src, i) => (
                      <tr key={i} className="hover:bg-zinc-800/30">
                        <td className="py-2 px-3 text-zinc-200 font-medium">{src.source_name}</td>
                        <td className="py-2 px-3 text-zinc-500 font-mono text-xs">{src.source_type}</td>
                        <td className="py-2 px-3">
                          <div className="flex flex-wrap gap-1">
                            {src.categories.map((c) => (
                              <span key={c} className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400">
                                {getShortLabel(c)}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="py-2 px-3 font-mono text-zinc-400">{src.record_count.toLocaleString()}</td>
                        <td className="py-2 px-3 text-zinc-500 text-[11px]">{fmtDate(src.last_fetched_at)}</td>
                        <td className="py-2 px-3">
                          <span className={`text-xs ${src.is_active ? 'text-emerald-400' : 'text-red-400'}`}>
                            {src.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Preemption Rules Tab — Matrix ── */}
      {tab === 'preemption' && (
        <div>
          {preemptionMatrix.states.length === 0 ? (
            <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
              <p className="text-sm text-zinc-600">No preemption rules in the database yet.</p>
            </div>
          ) : (
            <div className="border border-zinc-800 rounded-lg p-4">
              <p className="text-[11px] text-zinc-500 mb-3">
                Green = allows local override · Red = state preempts local law · Hover for notes
              </p>
              <div className="overflow-x-auto">
                <table className="text-xs">
                  <thead>
                    <tr>
                      <th className="py-1.5 px-2 text-left text-[10px] text-zinc-500 uppercase tracking-wide">State</th>
                      {requiredCats.map((c) => (
                        <th key={c} className="py-1.5 px-1.5 text-center text-[10px] text-zinc-500 uppercase tracking-wide whitespace-nowrap">
                          {getShortLabel(c)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preemptionMatrix.states.map((state) => (
                      <tr key={state} className="hover:bg-zinc-800/30">
                        <td className="py-1 px-2 font-mono font-bold text-zinc-200">{state}</td>
                        {requiredCats.map((cat) => {
                          const cell = preemptionMatrix.matrix[state]?.[cat]
                          if (!cell) return <td key={cat} className="py-1 px-1.5 text-center text-zinc-700">—</td>
                          const isHovered = hoveredCell?.state === state && hoveredCell?.cat === cat
                          return (
                            <td key={cat} className="py-1 px-1.5 text-center relative"
                              onMouseEnter={() => setHoveredCell({ state, cat })}
                              onMouseLeave={() => setHoveredCell(null)}>
                              <span className={`inline-flex items-center justify-center w-6 h-6 rounded text-[11px] font-bold ${
                                cell.allows ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'
                              }`}>
                                {cell.allows ? '✓' : '✗'}
                              </span>
                              {isHovered && cell.notes && (
                                <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2.5 py-1.5 rounded-lg text-[10px] max-w-[220px] bg-zinc-800 text-zinc-200 shadow-lg whitespace-normal">
                                  {cell.notes}
                                </div>
                              )}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Bookmarks Tab ── */}
      {tab === 'bookmarks' && (
        <div>
          {loadingBookmarks ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : bookmarks.length === 0 ? (
            <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
              <p className="text-sm text-zinc-600">No bookmarked requirements. Bookmark items from the Jurisdictions page.</p>
            </div>
          ) : (
            <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60 max-h-[70vh] overflow-y-auto">
              {bookmarks.map((req) => (
                <div key={req.id} className="flex items-start gap-3 px-4 py-2.5">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-zinc-200">{req.title}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[11px] text-zinc-400">{req.city}, {req.state}</span>
                      <span className="text-[11px] text-zinc-600">·</span>
                      <span className="text-[11px] text-zinc-500">{getCategoryLabel(req.category)}</span>
                      <span className="text-[11px] text-zinc-600">·</span>
                      <span className="text-[11px] text-zinc-500">{req.jurisdiction_level}</span>
                      {req.current_value && (
                        <>
                          <span className="text-[11px] text-zinc-600">·</span>
                          <span className="text-[11px] text-zinc-400">{req.current_value}</span>
                        </>
                      )}
                    </div>
                  </div>
                  <button type="button" onClick={() => toggleBookmark(req.id)}
                    className="text-xs text-zinc-600 hover:text-zinc-300 px-2 py-1 transition-colors shrink-0">
                    Unbookmark
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Profile Editor Modal */}
      <ProfileEditorModal
        open={profileModalOpen}
        onClose={() => setProfileModalOpen(false)}
        profiles={profiles}
        onCreate={createProfile}
        onUpdate={updateProfile}
        onDelete={removeProfile}
      />
    </div>
  )
}
