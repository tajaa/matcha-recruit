import { useEffect, useState, useCallback, useMemo } from 'react'
import { api } from '../../api/client'
import { postSSE } from '../../api/sse'
import { Button } from '../../components/ui'
import JurisdictionDetailPanel from '../../components/admin/JurisdictionDetailPanel'
import ExplorerTab from '../../components/admin/jurisdiction/ExplorerTab'
import PolicyBrowserTab from '../../components/admin/jurisdiction/PolicyBrowserTab'
import KeyIndexTab from '../../components/admin/jurisdiction/KeyIndexTab'
import IntegrityTab from '../../components/admin/jurisdiction/IntegrityTab'
import EvalsTab from '../../components/admin/jurisdiction/EvalsTab'
import PenaltyOverviewTab from '../../components/admin/jurisdiction/PenaltyOverviewTab'
import ProfileEditorModal from '../../components/admin/jurisdiction/ProfileEditorModal'
import SpecialtyFilterSelect from '../../components/admin/jurisdiction/SpecialtyFilterSelect'
import { useIndustryProfiles } from '../../components/admin/jurisdiction/useIndustryProfiles'
import { matchesSpecialty } from '../../components/admin/jurisdiction/utils'
import type { DataOverview, BookmarkedReq, FlatCity, CatCoverage, SpecialtyFilter } from '../../components/admin/jurisdiction/types'
import { getCategoryLabel, getShortLabel } from './JurisdictionData/helpers'
import type { Tab, ApiSourcesData } from './JurisdictionData/types'
import QualityTab from './JurisdictionData/QualityTab'
import PreemptionTab from './JurisdictionData/PreemptionTab'
import ApiSourcesTab from './JurisdictionData/ApiSourcesTab'
import BookmarksTab from './JurisdictionData/BookmarksTab'
import ScheduleRulesTab from './JurisdictionData/ScheduleRulesTab'

// ── Component ──────────────────────────────────────────────────────────────────

export default function JurisdictionData() {
  const [tab, setTab] = useState<Tab>('explorer')
  const [overview, setOverview] = useState<DataOverview | null>(null)
  const [loadingOverview, setLoadingOverview] = useState(true)
  const [selectedCityId, setSelectedCityId] = useState<string | null>(null)
  const [selectedCityMeta, setSelectedCityMeta] = useState<{ city: string; state: string; missing: string[] } | null>(null)
  const [apiSourcesData, setApiSourcesData] = useState<ApiSourcesData | null>(null)
  const [loadingApiSources, setLoadingApiSources] = useState(false)
  const [bookmarks, setBookmarks] = useState<BookmarkedReq[]>([])
  const [loadingBookmarks, setLoadingBookmarks] = useState(false)
  const [specialtyFilter, setSpecialtyFilter] = useState<SpecialtyFilter>('all')
  const [metroScanning, setMetroScanning] = useState(false)
  const [metroMessages, setMetroMessages] = useState<string[]>([])
  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null)

  const { profiles, create: createProfile, update: updateProfile, remove: removeProfile } = useIndustryProfiles()
  const selectedProfile = profiles.find((p) => p.id === selectedProfileId) ?? null

  const fetchOverview = useCallback(async (bust = false) => {
    setLoadingOverview(true)
    const qs = bust ? '?bust=true' : ''
    try { setOverview(await api.get<DataOverview>(`/admin/jurisdictions/data-overview${qs}`)) }
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
    postSSE(
      '/admin/jurisdictions/top-metros/check',
      undefined,
      (data) => {
        const ev = data as { type?: string; message?: string; city?: string; state?: string }
        if (ev.type === 'run_completed') return true
        const msg = ev.message || (ev.city && `${ev.city}, ${ev.state}`) || null
        if (msg) setMetroMessages((p) => [...p, msg])
      },
    )
      .then(() => fetchOverview())
      .catch(() => {})
      .finally(() => setMetroScanning(false))
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
          country_code: city.country_code || st.country_code || 'US',
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

  const stateOptions = useMemo(() => [...new Set(allStates.map((s) => s.state))].sort(), [allStates])

  if (loadingOverview) return <p className="text-sm text-zinc-500">Loading...</p>
  if (!overview || !sum) return <p className="text-sm text-zinc-600">Failed to load data. Check that the server is running and you're logged in as admin.</p>

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Compliance Library</h1>
          <p className="mt-1 text-sm text-zinc-500">The codified compliance data — values, quality, keys, and evals</p>
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
          <Button variant="ghost" size="sm" onClick={() => fetchOverview(true)}>Refresh</Button>
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
          { label: 'Jurisdictions', value: sum.total_cities.toLocaleString() },
          { label: 'Requirements', value: sum.total_requirements.toLocaleString() },
          { label: 'Coverage', value: `${sum.category_coverage_pct}%`, color: sum.category_coverage_pct >= 70 ? 'text-emerald-400' : sum.category_coverage_pct >= 40 ? 'text-amber-400' : 'text-red-400' },
          { label: 'Key Definitions', value: '353' },
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
          { id: 'evals' as Tab, label: 'Evals' },
          { id: 'key-index' as Tab, label: 'Key Index' },
          { id: 'integrity' as Tab, label: 'Integrity' },
          { id: 'penalties' as Tab, label: 'Penalties' },
          { id: 'preemption' as Tab, label: 'Preemption' },
          { id: 'api-sources' as Tab, label: 'API Sources' },
          { id: 'bookmarks' as Tab, label: 'Bookmarks' },
          { id: 'schedule-rules' as Tab, label: 'Schedule Rules' },
        ]).map((t) => (
          <Button key={t.id} variant={tab === t.id ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t.id)}>
            {t.label}
          </Button>
        ))}
      </div>

      {/* ── Policies Tab ── */}
      {tab === 'policies' && <PolicyBrowserTab />}

      {/* ── Evals Tab ── */}
      {tab === 'evals' && <EvalsTab />}

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
      {tab === 'quality' && <QualityTab />}

      {/* ── Key Index Tab ── */}
      {tab === 'key-index' && <KeyIndexTab />}

      {/* ── Integrity Tab ── */}
      {tab === 'integrity' && <IntegrityTab />}

      {/* ── Penalties Tab ── */}
      {tab === 'penalties' && <PenaltyOverviewTab />}

      {/* ── Preemption Rules Tab — Matrix ── */}
      {tab === 'preemption' && (
        <PreemptionTab requiredCats={requiredCats} preemptionRules={overview.preemption_rules} />
      )}

      {/* ── API Sources Tab ── */}
      {tab === 'api-sources' && (
        <ApiSourcesTab data={apiSourcesData} loading={loadingApiSources} />
      )}

      {/* ── Bookmarks Tab ── */}
      {tab === 'bookmarks' && (
        <BookmarksTab
          bookmarks={bookmarks}
          loading={loadingBookmarks}
          allCities={allCities}
          onNavigateToCity={(cityFlat) => { setTab('explorer'); openCity(cityFlat) }}
          onToggleBookmark={toggleBookmark}
        />
      )}

      {tab === 'schedule-rules' && <ScheduleRulesTab />}

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
