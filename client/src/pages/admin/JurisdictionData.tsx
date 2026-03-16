import { useEffect, useState, useCallback, useMemo } from 'react'
import { api } from '../../api/client'
import { Button, Input } from '../../components/ui'
import { categoryLabel } from '../../types/compliance'
import type { RequirementCategory } from '../../types/compliance'
import JurisdictionDetailPanel from '../../components/admin/JurisdictionDetailPanel'

// ── Types ──────────────────────────────────────────────────────────────────────

type CityEntry = {
  id: string
  city: string
  categories_present: string[]
  categories_missing: string[]
  tier_breakdown: Record<string, number>
  last_verified_at: string | null
  is_stale: boolean
}

type StateEntry = {
  state: string
  city_count: number
  coverage_pct: number
  cities: CityEntry[]
}

type PreemptionRule = {
  state: string
  category: string
  allows_local_override: boolean
  notes: string | null
}

type StructuredSource = {
  source_name: string
  source_type: string
  categories: string[]
  record_count: number
  last_fetched_at: string | null
  last_fetch_status: string | null
  is_active: boolean
}

type DataOverview = {
  summary: {
    total_states: number
    total_cities: number
    total_requirements: number
    category_coverage_pct: number
    tier1_pct: number
    tier_breakdown: Record<string, number>
    stale_count: number
    freshness: { '7d': number; '30d': number; '90d': number; stale: number }
    required_categories: string[]
  }
  states: StateEntry[]
  preemption_rules: PreemptionRule[]
  structured_sources: StructuredSource[]
}

type BookmarkedReq = {
  id: string
  category: string
  jurisdiction_level: string
  title: string
  current_value: string | null
  effective_date: string | null
  city: string
  state: string
}

type Tab = 'coverage' | 'missing' | 'quality' | 'preemption' | 'bookmarks'

function getCategoryLabel(cat: string) {
  return categoryLabel[cat as RequirementCategory] ?? cat
}

const SHORT_LABELS: Record<string, string> = {
  // General labor
  minimum_wage: 'Wage', overtime: 'OT', sick_leave: 'Sick', family_leave: 'FMLA',
  anti_discrimination: 'Disc', workplace_safety: 'Safety', workers_comp: 'WC',
  tax_withholding: 'Tax', pay_frequency: 'Pay', meal_breaks: 'Meals',
  rest_breaks: 'Rest', final_pay: 'Final', posting_requirements: 'Post',
  pto: 'PTO', fair_scheduling: 'Sched', ban_the_box: 'BtB', non_compete: 'NC',
  harassment_training: 'Train', data_privacy: 'Priv', whistleblower: 'Whistle',
  accommodations: 'ADA', minor_work_permit: 'Minor', scheduling_reporting: 'Sched',
  // Healthcare
  hipaa_privacy: 'HIPAA', billing_integrity: 'Billing', clinical_safety: 'Clinical',
  healthcare_workforce: 'HC Workforce', corporate_integrity: 'Corp Integrity',
  research_consent: 'Research', state_licensing: 'Licensing', emergency_preparedness: 'Emergency',
  // Oncology
  radiation_safety: 'Radiation', chemotherapy_handling: 'Chemo', tumor_registry: 'Tumor',
  oncology_clinical_trials: 'Onc Trials', oncology_patient_rights: 'Onc Rights',
  other: 'Other',
}

const HEALTHCARE_CATS = new Set([
  'hipaa_privacy', 'billing_integrity', 'clinical_safety', 'healthcare_workforce',
  'corporate_integrity', 'research_consent', 'state_licensing', 'emergency_preparedness',
])
const ONCOLOGY_CATS = new Set([
  'radiation_safety', 'chemotherapy_handling', 'tumor_registry',
  'oncology_clinical_trials', 'oncology_patient_rights',
])

type SpecialtyFilter = 'all' | 'general' | 'healthcare' | 'oncology'

function fmtDate(d: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function JurisdictionData() {
  const [tab, setTab] = useState<Tab>('coverage')
  const [overview, setOverview] = useState<DataOverview | null>(null)
  const [loadingOverview, setLoadingOverview] = useState(true)
  const [search, setSearch] = useState('')
  const [expandedStates, setExpandedStates] = useState<Set<string>>(new Set())
  const [selectedCityId, setSelectedCityId] = useState<string | null>(null)
  const [selectedCityMeta, setSelectedCityMeta] = useState<{ city: string; state: string; missing: string[] } | null>(null)
  const [bookmarks, setBookmarks] = useState<BookmarkedReq[]>([])
  const [loadingBookmarks, setLoadingBookmarks] = useState(false)

  // Filters
  const [specialtyFilter, setSpecialtyFilter] = useState<SpecialtyFilter>('all')
  const [filterState, setFilterState] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterStaleOnly, setFilterStaleOnly] = useState(false)

  // Preemption matrix hover
  const [hoveredCell, setHoveredCell] = useState<{ state: string; cat: string } | null>(null)

  // Top metro SSE
  const [metroScanning, setMetroScanning] = useState(false)
  const [metroMessages, setMetroMessages] = useState<string[]>([])

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

  function toggleState(state: string) {
    setExpandedStates((prev) => {
      const next = new Set(prev)
      next.has(state) ? next.delete(state) : next.add(state)
      return next
    })
  }

  function openCity(cityEntry: CityEntry, state: string) {
    setSelectedCityId(cityEntry.id)
    setSelectedCityMeta({ city: cityEntry.city, state, missing: cityEntry.categories_missing })
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
  // Filter categories by specialty
  const requiredCats = useMemo(() => {
    if (specialtyFilter === 'all') return allRequiredCats
    if (specialtyFilter === 'healthcare') return allRequiredCats.filter((c) => HEALTHCARE_CATS.has(c) || ONCOLOGY_CATS.has(c))
    if (specialtyFilter === 'oncology') return allRequiredCats.filter((c) => ONCOLOGY_CATS.has(c))
    // general = exclude healthcare & oncology
    return allRequiredCats.filter((c) => !HEALTHCARE_CATS.has(c) && !ONCOLOGY_CATS.has(c))
  }, [allRequiredCats, specialtyFilter])
  const allStates = overview?.states ?? []

  const filteredStates = useMemo(() => {
    return allStates.filter((s) => {
      if (!search) return true
      const q = search.toLowerCase()
      return s.state.toLowerCase().includes(q) || s.cities.some((c) => c.city.toLowerCase().includes(q))
    })
  }, [allStates, search])

  // Missing data: cities sorted by most missing categories, filtered by specialty + category
  const missingCities = useMemo(() => {
    const rows: (CityEntry & { stateName: string; filteredMissing: string[] })[] = []
    for (const st of allStates) {
      if (filterState && st.state !== filterState) continue
      for (const city of st.cities) {
        // Filter missing categories by specialty
        let missing = city.categories_missing
        if (specialtyFilter === 'healthcare') missing = missing.filter((c) => HEALTHCARE_CATS.has(c) || ONCOLOGY_CATS.has(c))
        else if (specialtyFilter === 'oncology') missing = missing.filter((c) => ONCOLOGY_CATS.has(c))
        else if (specialtyFilter === 'general') missing = missing.filter((c) => !HEALTHCARE_CATS.has(c) && !ONCOLOGY_CATS.has(c))
        if (filterCategory && !missing.includes(filterCategory)) continue
        if (missing.length === 0) continue
        if (filterStaleOnly && !city.is_stale) continue
        rows.push({ ...city, stateName: st.state, filteredMissing: missing })
      }
    }
    return rows.sort((a, b) => b.filteredMissing.length - a.filteredMissing.length)
  }, [allStates, filterState, filterStaleOnly, specialtyFilter, filterCategory])

  // Preemption matrix: state → category → { allows, notes }
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

  // Unique states for missing data filter
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
          <select value={specialtyFilter} onChange={(e) => setSpecialtyFilter(e.target.value as SpecialtyFilter)}
            className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5">
            <option value="all">All Specialties</option>
            <option value="general">General Labor</option>
            <option value="healthcare">Healthcare</option>
            <option value="oncology">Oncology</option>
          </select>
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
          { id: 'coverage' as Tab, label: 'Coverage' },
          { id: 'missing' as Tab, label: `Missing Data${missingCities.length ? ` (${missingCities.length})` : ''}` },
          { id: 'quality' as Tab, label: 'Data Quality' },
          { id: 'preemption' as Tab, label: 'Preemption' },
          { id: 'bookmarks' as Tab, label: 'Bookmarks' },
        ]).map((t) => (
          <Button key={t.id} variant={tab === t.id ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t.id)}>
            {t.label}
          </Button>
        ))}
      </div>

      {/* ── Coverage Tab ── */}
      {tab === 'coverage' && (
        <div className={selectedCityId ? 'grid grid-cols-5 gap-4' : ''}>
          <div className={selectedCityId ? 'col-span-2' : ''}>
            <div className="border border-zinc-800 rounded-lg">
              {/* Search */}
              <div className="px-3 py-2 border-b border-zinc-800/60">
                <Input label="" placeholder="Filter states / cities..." value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>

              {/* Category legend */}
              {requiredCats.length > 0 && !selectedCityId && (
                <div className="px-3 py-2 border-b border-zinc-800/60 flex flex-wrap gap-x-3 gap-y-1">
                  {requiredCats.map((cat) => (
                    <span key={cat} className="text-[10px] text-zinc-500 font-medium" title={getCategoryLabel(cat)}>
                      {SHORT_LABELS[cat] || cat}
                    </span>
                  ))}
                </div>
              )}

              {/* State rows */}
              <div className="max-h-[60vh] overflow-y-auto divide-y divide-zinc-800/60">
                {filteredStates.map((s) => {
                  const isOpen = expandedStates.has(s.state) || !!search
                  const citiesToShow = search
                    ? s.cities.filter((c) => c.city.toLowerCase().includes(search.toLowerCase()))
                    : s.cities
                  return (
                    <div key={s.state}>
                      <button type="button" onClick={() => { if (!search) toggleState(s.state) }}
                        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-zinc-800/30 transition-colors">
                        <span className="text-zinc-600 w-4 text-center text-xs">{isOpen ? '▾' : '▸'}</span>
                        <span className="text-sm font-bold text-zinc-200 w-8 font-mono">{s.state}</span>
                        <span className="text-[11px] text-zinc-500 w-16">{s.city_count} {s.city_count === 1 ? 'city' : 'cities'}</span>
                        <div className="flex-1 flex items-center gap-2">
                          <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${s.coverage_pct >= 80 ? 'bg-emerald-500' : s.coverage_pct >= 50 ? 'bg-amber-400' : 'bg-red-400'}`}
                              style={{ width: `${s.coverage_pct}%` }}
                            />
                          </div>
                          <span className="text-[11px] font-mono text-zinc-500 w-10 text-right">{s.coverage_pct}%</span>
                        </div>
                      </button>

                      {isOpen && citiesToShow.length > 0 && (
                        <div className="bg-zinc-900/30 border-t border-zinc-800/40">
                          {citiesToShow.map((city) => (
                            <button key={city.id} type="button"
                              onClick={() => openCity(city, s.state)}
                              className={`w-full flex items-center gap-2 px-4 py-1.5 text-left transition-colors group ${
                                selectedCityId === city.id ? 'bg-zinc-800/60' : 'hover:bg-zinc-800/30'
                              }`}>
                              <span className={`text-sm w-36 truncate ${city.is_stale ? 'text-amber-300/80' : 'text-zinc-300'}`}>
                                {city.city}
                              </span>
                              {/* Category dots */}
                              <div className="flex gap-1">
                                {requiredCats.map((cat) => (
                                  <div key={cat}
                                    className={`w-2.5 h-2.5 rounded-full ${city.categories_present.includes(cat) ? 'bg-emerald-500' : 'bg-red-500/60'}`}
                                    title={`${getCategoryLabel(cat)}: ${city.categories_present.includes(cat) ? 'Present' : 'Missing'}`}
                                  />
                                ))}
                              </div>
                              <span className="text-[11px] font-mono text-zinc-600 ml-auto">{fmtDate(city.last_verified_at)}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>

          {/* City detail panel */}
          {selectedCityId && selectedCityMeta && (
            <div className="col-span-3">
              <div className="flex items-center justify-between mb-2">
                <button type="button" onClick={() => { setSelectedCityId(null); setSelectedCityMeta(null) }}
                  className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">← Back to list</button>
              </div>
              <JurisdictionDetailPanel
                id={selectedCityId}
                city={selectedCityMeta.city}
                state={selectedCityMeta.state}
                categoriesMissing={selectedCityMeta.missing}
                onCheckComplete={fetchOverview}
              />
            </div>
          )}
        </div>
      )}

      {/* ── Missing Data Tab ── */}
      {tab === 'missing' && (
        <div>
          {/* Filters */}
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <select value={filterState} onChange={(e) => setFilterState(e.target.value)}
              className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5">
              <option value="">All States</option>
              {stateOptions.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}
              className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5">
              <option value="">All Categories</option>
              {requiredCats.map((c) => <option key={c} value={c}>{SHORT_LABELS[c] || getCategoryLabel(c)}</option>)}
            </select>
            <button type="button" onClick={() => setFilterStaleOnly(!filterStaleOnly)}
              className={`text-xs px-2.5 py-1 rounded transition-colors ${filterStaleOnly ? 'bg-amber-500/20 text-amber-400' : 'text-zinc-500 hover:text-zinc-300'}`}>
              Stale only
            </button>
            <span className="text-[11px] text-zinc-600 ml-auto">{missingCities.length} jurisdictions</span>
          </div>

          {missingCities.length === 0 ? (
            <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
              <p className="text-sm text-zinc-600">
                {filterState || filterStaleOnly || filterCategory ? 'No cities match these filters.' : 'All cities have complete category coverage.'}
              </p>
            </div>
          ) : (
            <div className="border border-zinc-800 rounded-lg overflow-hidden">
              <div className="max-h-[70vh] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-zinc-900/50 text-zinc-400 sticky top-0">
                    <tr>
                      <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">ST</th>
                      <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">City</th>
                      <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Missing</th>
                      <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Gaps</th>
                      <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide">Verified</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {missingCities.slice(0, 100).map((city) => (
                      <tr key={city.id} className="hover:bg-zinc-800/30 cursor-pointer"
                        onClick={() => { setSelectedCityId(city.id); setSelectedCityMeta({ city: city.city, state: city.stateName, missing: city.filteredMissing }); setTab('coverage') }}>
                        <td className="py-2 px-3 font-mono font-bold text-zinc-200">{city.stateName}</td>
                        <td className="py-2 px-3 text-zinc-200 hover:underline">{city.city}</td>
                        <td className="py-2 px-3">
                          <div className="flex flex-wrap gap-1">
                            {city.filteredMissing.map((cat) => (
                              <span key={cat} className="text-[10px] text-red-400/70 bg-red-500/10 px-1.5 py-0.5 rounded">
                                {SHORT_LABELS[cat] || getCategoryLabel(cat)}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className={`py-2 px-3 font-mono ${city.filteredMissing.length >= 4 ? 'text-red-400' : 'text-amber-400'}`}>
                          {city.filteredMissing.length}/{requiredCats.length}
                        </td>
                        <td className="py-2 px-3 text-zinc-500 whitespace-nowrap text-[11px]">
                          {fmtDate(city.last_verified_at)}
                          {city.is_stale && <span className="text-amber-400/70 ml-1">⚠</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {missingCities.length > 100 && (
                  <p className="text-center py-2 text-[10px] text-zinc-600">Showing 100 of {missingCities.length}</p>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Data Quality Tab ── */}
      {tab === 'quality' && (
        <div className="space-y-5">
          {/* Tier breakdown with bars */}
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

          {/* Freshness */}
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

          {/* Structured Data Sources */}
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
                                {SHORT_LABELS[c] || getCategoryLabel(c)}
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
                          {SHORT_LABELS[c] || c}
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
    </div>
  )
}
