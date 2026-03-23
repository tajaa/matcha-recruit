import { Fragment, useEffect, useState, useCallback, useMemo } from 'react'
import { api } from '../../api/client'
import { Button } from '../../components/ui'
import {
  CATEGORY_LABELS,
  CATEGORY_SHORT_LABELS,
} from '../../generated/complianceCategories'
import JurisdictionDetailPanel from '../../components/admin/JurisdictionDetailPanel'
import ExplorerTab from '../../components/admin/jurisdiction/ExplorerTab'
import PolicyBrowserTab from '../../components/admin/jurisdiction/PolicyBrowserTab'
import CoverageHeatmap from '../../components/admin/jurisdiction/CoverageHeatmap'
import RequirementAuditTable from '../../components/admin/jurisdiction/RequirementAuditTable'
import GapIntelligencePanel from '../../components/admin/jurisdiction/GapIntelligencePanel'
import KeyCoverageDrawer from '../../components/admin/jurisdiction/KeyCoverageDrawer'
import KeyIndexTab from '../../components/admin/jurisdiction/KeyIndexTab'
import IntegrityTab from '../../components/admin/jurisdiction/IntegrityTab'
import ProfileEditorModal from '../../components/admin/jurisdiction/ProfileEditorModal'
import SpecialtyFilterSelect from '../../components/admin/jurisdiction/SpecialtyFilterSelect'
import { useIndustryProfiles } from '../../components/admin/jurisdiction/useIndustryProfiles'
import { fmtDate, matchesSpecialty } from '../../components/admin/jurisdiction/utils'
import type { DataOverview, BookmarkedReq, FlatCity, CatCoverage, SpecialtyFilter } from '../../components/admin/jurisdiction/types'

// ── Types ──────────────────────────────────────────────────────────────────────

type Tab = 'explorer' | 'policies' | 'quality' | 'key-index' | 'integrity' | 'preemption' | 'bookmarks' | 'api-sources'

type SourceCount = {
  research_source: string
  total: number
  category_count: number
  jurisdiction_count: number
  earliest: string | null
  latest: string | null
}

type ApiReqRow = {
  id: string
  category: string
  title: string
  description: string | null
  current_value: string | null
  source_name: string | null
  source_url: string | null
  effective_date: string | null
  created_at: string | null
  updated_at: string | null
  jurisdiction_level: string
  jurisdiction_name: string | null
  last_verified_at: string | null
  city: string
  state: string
}

type ApiSourcesData = {
  source_counts: SourceCount[]
  recent_api: ApiReqRow[]
  api_by_category: { category: string; count: number }[]
}

function getCategoryLabel(cat: string) {
  return CATEGORY_LABELS[cat] ?? cat
}

function getShortLabel(cat: string) {
  return CATEGORY_SHORT_LABELS[cat] ?? cat
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function JurisdictionData() {
  const [tab, setTab] = useState<Tab>('explorer')
  const [qualityView, setQualityView] = useState<'heatmap' | 'table' | 'gaps'>('heatmap')
  const [keyCoverageDrawer, setKeyCoverageDrawer] = useState<{
    jurisdictionId?: string; category?: string
  } | null>(null)
  const [overview, setOverview] = useState<DataOverview | null>(null)
  const [loadingOverview, setLoadingOverview] = useState(true)
  const [selectedCityId, setSelectedCityId] = useState<string | null>(null)
  const [selectedCityMeta, setSelectedCityMeta] = useState<{ city: string; state: string; missing: string[] } | null>(null)
  const [apiSourcesData, setApiSourcesData] = useState<ApiSourcesData | null>(null)
  const [loadingApiSources, setLoadingApiSources] = useState(false)
  const [expandedApiRow, setExpandedApiRow] = useState<string | null>(null)
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

  const fetchApiSources = useCallback(async () => {
    setLoadingApiSources(true)
    try { setApiSourcesData(await api.get<ApiSourcesData>('/admin/jurisdictions/api-sources')) }
    catch { setApiSourcesData(null) }
    finally { setLoadingApiSources(false) }
  }, [])

  useEffect(() => { fetchOverview() }, [fetchOverview])
  useEffect(() => { if (tab === 'bookmarks') fetchBookmarks() }, [tab, fetchBookmarks])
  useEffect(() => { if (tab === 'api-sources') fetchApiSources() }, [tab, fetchApiSources])

  async function handleDeleteCity(id: string) {
    await api.delete(`/admin/jurisdictions/${id}`)
    if (selectedCityId === id) {
      setSelectedCityId(null)
      setSelectedCityMeta(null)
    }
    await fetchOverview()
  }

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
          presentCount: present.length,
          totalCount: total,
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
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk] tracking-tight">Jurisdiction Data</h1>
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
          <SpecialtyFilterSelect
            value={specialtyFilter}
            onChange={setSpecialtyFilter}
            className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5"
          />
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
          { id: 'policies' as Tab, label: 'Policies' },
          { id: 'quality' as Tab, label: 'Data Quality' },
          { id: 'key-index' as Tab, label: 'Key Index' },
          { id: 'integrity' as Tab, label: 'Integrity' },
          { id: 'preemption' as Tab, label: 'Preemption' },
          { id: 'api-sources' as Tab, label: 'API Sources' },
          { id: 'bookmarks' as Tab, label: 'Bookmarks' },
        ]).map((t) => (
          <Button key={t.id} variant={tab === t.id ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t.id)}>
            {t.label}
          </Button>
        ))}
      </div>

      {/* ── Policies Tab ── */}
      {tab === 'policies' && <PolicyBrowserTab />}

      {/* ── Explorer Tab ── */}
      {tab === 'explorer' && (
        <>
          <ExplorerTab
            allCities={allCities}
            categoryCoverage={categoryCoverage}
            stateOptions={stateOptions}
            onSelectCity={openCity}
            selectedCityId={selectedCityId}
            onDelete={handleDeleteCity}
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
                onNavigate={(targetId) => {
                  // Navigate to the target jurisdiction (e.g., state-level parent)
                  const flat = allCities.find((c) => c.id === targetId)
                  if (flat) {
                    openCity(flat)
                  } else {
                    // Target might be a state-level row not in allCities — open it directly
                    setSelectedCityId(targetId)
                    setSelectedCityMeta({ city: '', state: selectedCityMeta.state, missing: [] })
                  }
                }}
              />
            </div>
          )}
        </>
      )}

      {/* ── Data Quality Tab ── */}
      {tab === 'quality' && (
        <div className="space-y-4">
          {/* Segmented control */}
          <div className="flex items-center gap-1">
            {([
              { id: 'heatmap' as const, label: 'Heatmap' },
              { id: 'table' as const, label: 'Audit Table' },
              { id: 'gaps' as const, label: 'Gaps' },
            ]).map((v) => (
              <Button
                key={v.id}
                variant={qualityView === v.id ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setQualityView(v.id)}
              >
                {v.label}
              </Button>
            ))}
            <div className="ml-auto">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setKeyCoverageDrawer({})}
              >
                Key Coverage
              </Button>
            </div>
          </div>

          {qualityView === 'heatmap' && (
            <CoverageHeatmap
              onCellClick={(jurisdictionId, category) => {
                setKeyCoverageDrawer({ jurisdictionId, category })
              }}
            />
          )}

          {keyCoverageDrawer && (
            <KeyCoverageDrawer
              jurisdictionId={keyCoverageDrawer.jurisdictionId}
              category={keyCoverageDrawer.category}
              onClose={() => setKeyCoverageDrawer(null)}
            />
          )}

          {qualityView === 'table' && (
            <RequirementAuditTable
              onEditRequirement={(requirementId) => {
                // Open the jurisdiction that owns this requirement in the detail panel
                // For now log — full wiring would require a req→jurisdiction lookup
                console.log('[Quality] Edit requirement:', requirementId)
              }}
            />
          )}

          {qualityView === 'gaps' && <GapIntelligencePanel />}
        </div>
      )}

      {/* ── Key Index Tab ── */}
      {tab === 'key-index' && <KeyIndexTab />}

      {/* ── Integrity Tab ── */}
      {tab === 'integrity' && <IntegrityTab />}

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

      {/* ── API Sources Tab ── */}
      {tab === 'api-sources' && (
        <div className="space-y-5">
          {loadingApiSources ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : !apiSourcesData ? (
            <p className="text-sm text-zinc-600">Failed to load API sources data.</p>
          ) : (
            <>
              {/* Research source breakdown */}
              <div>
                <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">Requirements by Research Source</h2>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {apiSourcesData.source_counts.map((s) => {
                    const colors: Record<string, string> = {
                      official_api: 'text-emerald-400 border-emerald-500/30',
                      gemini: 'text-purple-400 border-purple-500/30',
                      claude_skill: 'text-blue-400 border-blue-500/30',
                      structured: 'text-amber-400 border-amber-500/30',
                      manual: 'text-zinc-300 border-zinc-600',
                      unknown: 'text-zinc-500 border-zinc-700',
                    }
                    const labels: Record<string, string> = {
                      official_api: 'Official APIs',
                      gemini: 'Gemini AI',
                      claude_skill: 'Claude Skill',
                      structured: 'Structured Data',
                      manual: 'Manual',
                      unknown: 'Untagged',
                    }
                    const color = colors[s.research_source] || colors.unknown
                    return (
                      <div key={s.research_source} className={`border rounded-lg px-3 py-3 ${color}`}>
                        <p className="text-[10px] uppercase tracking-wider font-medium opacity-70">
                          {labels[s.research_source] || s.research_source}
                        </p>
                        <p className="text-2xl font-bold tracking-tight mt-0.5">{s.total.toLocaleString()}</p>
                        <p className="text-[10px] opacity-60 mt-0.5">
                          {s.category_count} categories · {s.jurisdiction_count} jurisdictions
                        </p>
                        {s.latest && (
                          <p className="text-[10px] opacity-40 mt-0.5">Last: {fmtDate(s.latest)}</p>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Official API category breakdown */}
              {apiSourcesData.api_by_category.length > 0 && (
                <div>
                  <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">
                    Official API Data by Category
                  </h2>
                  <div className="border border-zinc-800 rounded-lg p-4">
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                      {apiSourcesData.api_by_category.map((c) => (
                        <div key={c.category} className="flex items-center justify-between px-2 py-1.5 rounded bg-zinc-900/50">
                          <span className="text-[11px] text-zinc-300">{getCategoryLabel(c.category)}</span>
                          <span className="text-[11px] font-mono font-bold text-emerald-400">{c.count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Recent official API entries */}
              {apiSourcesData.recent_api.length > 0 && (
                <div>
                  <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">
                    Recent Official API Entries ({apiSourcesData.recent_api.length})
                  </h2>
                  <div className="border border-zinc-800 rounded-lg overflow-hidden">
                    <div className="max-h-[50vh] overflow-y-auto">
                      <table className="w-full text-sm">
                        <thead className="bg-zinc-900/50 text-zinc-400 sticky top-0">
                          <tr>
                            <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Title</th>
                            <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Category</th>
                            <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Location</th>
                            <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Source</th>
                            <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Updated</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-800">
                          {apiSourcesData.recent_api.map((r) => (
                            <Fragment key={r.id}>
                              <tr className="hover:bg-zinc-800/30 cursor-pointer" onClick={() => setExpandedApiRow(expandedApiRow === r.id ? null : r.id)}>
                                <td className="py-2 px-3 text-zinc-200 max-w-xs">
                                  <p className="truncate text-[11px]">
                                    <span className="text-zinc-600 mr-1">{expandedApiRow === r.id ? '▾' : '▸'}</span>
                                    {r.title}
                                  </p>
                                </td>
                                <td className="py-2 px-3">
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 whitespace-nowrap">
                                    {getShortLabel(r.category)}
                                  </span>
                                </td>
                                <td className="py-2 px-3 text-zinc-400 text-[11px] whitespace-nowrap">
                                  {r.city ? `${r.city}, ${r.state}` : r.state} · {r.jurisdiction_level}
                                </td>
                                <td className="py-2 px-3 text-[11px]">
                                  {r.source_url ? (
                                    <a href={r.source_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
                                      className="text-emerald-500/70 hover:text-emerald-400 underline">{r.source_name || 'Link'}</a>
                                  ) : (
                                    <span className="text-zinc-600">{r.source_name || '—'}</span>
                                  )}
                                </td>
                                <td className="py-2 px-3 text-zinc-500 text-[11px] whitespace-nowrap">
                                  {r.updated_at ? fmtDate(r.updated_at) : r.created_at ? fmtDate(r.created_at) : '—'}
                                </td>
                              </tr>
                              {expandedApiRow === r.id && (
                                <tr className="bg-zinc-900/40">
                                  <td colSpan={5} className="px-4 py-3">
                                    <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-[11px]">
                                      {r.description && (
                                        <div className="col-span-2">
                                          <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Description</p>
                                          <p className="text-zinc-300 leading-relaxed">{r.description}</p>
                                        </div>
                                      )}
                                      {r.current_value && (
                                        <div>
                                          <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Current Value</p>
                                          <p className="text-zinc-300">{r.current_value}</p>
                                        </div>
                                      )}
                                      <div>
                                        <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Category</p>
                                        <p className="text-zinc-300">{getCategoryLabel(r.category)}</p>
                                      </div>
                                      <div>
                                        <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Jurisdiction</p>
                                        <p className="text-zinc-300">{r.jurisdiction_name || r.jurisdiction_level} · {r.city ? `${r.city}, ${r.state}` : r.state}</p>
                                      </div>
                                      {r.effective_date && (
                                        <div>
                                          <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Effective Date</p>
                                          <p className="text-zinc-300">{r.effective_date}</p>
                                        </div>
                                      )}
                                      <div>
                                        <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Added</p>
                                        <p className="text-zinc-300">{r.created_at ? fmtDate(r.created_at) : '—'}</p>
                                      </div>
                                      {r.last_verified_at && (
                                        <div>
                                          <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Last Verified</p>
                                          <p className="text-zinc-300">{fmtDate(r.last_verified_at)}</p>
                                        </div>
                                      )}
                                      {r.source_url && (
                                        <div className="col-span-2">
                                          <p className="text-zinc-500 text-[10px] uppercase tracking-wider mb-0.5">Source URL</p>
                                          <a href={r.source_url} target="_blank" rel="noreferrer"
                                            className="text-emerald-500/70 hover:text-emerald-400 underline break-all">{r.source_url}</a>
                                        </div>
                                      )}
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </Fragment>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}

              {apiSourcesData.source_counts.length === 0 && apiSourcesData.recent_api.length === 0 && (
                <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
                  <p className="text-sm text-zinc-600">No research source data yet. Use the "Fed Sources" button on a jurisdiction to fetch from government APIs.</p>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Bookmarks Tab ── */}
      {tab === 'bookmarks' && (() => {
        // Group bookmarks by state → city
        const grouped: Record<string, Record<string, BookmarkedReq[]>> = {}
        let stateCount = 0
        for (const b of bookmarks) {
          if (!grouped[b.state]) { grouped[b.state] = {}; stateCount++ }
          if (!grouped[b.state][b.city]) grouped[b.state][b.city] = []
          grouped[b.state][b.city].push(b)
        }
        return (
          <div>
            {loadingBookmarks ? (
              <p className="text-sm text-zinc-500">Loading...</p>
            ) : bookmarks.length === 0 ? (
              <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
                <p className="text-sm text-zinc-600">No bookmarked requirements. Bookmark items from the Jurisdictions page.</p>
              </div>
            ) : (
              <>
                <p className="text-[11px] text-zinc-500 mb-2">
                  {bookmarks.length} bookmarked requirement{bookmarks.length !== 1 ? 's' : ''} across {stateCount} state{stateCount !== 1 ? 's' : ''}
                </p>
                <div className="border border-zinc-800 rounded-lg max-h-[70vh] overflow-y-auto">
                  {Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b)).map(([st, cities]) => (
                    <div key={st}>
                      <div className="px-4 pt-3 pb-1 bg-zinc-900/50 sticky top-0">
                        <p className="text-xs uppercase tracking-wide text-zinc-400 font-medium">{st}</p>
                      </div>
                      {Object.entries(cities).sort(([a], [b]) => a.localeCompare(b)).map(([cityName, reqs]) => (
                        <div key={cityName}>
                          <div className="px-4 pt-2 pb-1">
                            <button
                              type="button"
                              className="text-[11px] text-blue-400 hover:text-blue-300 transition-colors"
                              onClick={() => {
                                const cityFlat = allCities.find(c => c.city === cityName && c.stateName === st)
                                if (cityFlat) {
                                  setTab('explorer')
                                  openCity(cityFlat)
                                }
                              }}
                            >
                              {cityName} →
                            </button>
                          </div>
                          <div className="divide-y divide-zinc-800/60">
                            {reqs.map((req) => (
                              <div key={req.id} className="flex items-start gap-3 px-4 py-2.5">
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm text-zinc-200">{req.title}</p>
                                  {req.description && (
                                    <p className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2">{req.description}</p>
                                  )}
                                  <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400">
                                      {getShortLabel(req.category)}
                                    </span>
                                    <span className="text-[11px] text-zinc-500">{req.jurisdiction_level}</span>
                                    {req.current_value && <span className="text-[11px] text-zinc-400">{req.current_value}</span>}
                                    {req.effective_date && <span className="text-[11px] text-zinc-600">eff. {req.effective_date}</span>}
                                    {req.last_verified_at && <span className="text-[11px] text-zinc-600">verified {fmtDate(req.last_verified_at)}</span>}
                                    {req.source_name && (
                                      req.source_url
                                        ? <a href={req.source_url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-zinc-600 hover:text-zinc-400 underline">{req.source_name}</a>
                                        : <span className="text-[11px] text-zinc-600">{req.source_name}</span>
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
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )
      })()}

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
