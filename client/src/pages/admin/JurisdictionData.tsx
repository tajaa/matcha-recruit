import { useEffect, useState, useCallback } from 'react'
import { api } from '../../api/client'
import { Button, Input } from '../../components/ui'
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
  }
  states: StateEntry[]
}

type CoverageRequest = {
  id: string
  city: string
  state: string
  county: string | null
  status: string
  company_name: string
  employee_count: number
  admin_notes: string | null
  created_at: string | null
}

type Tab = 'overview' | 'jurisdictions' | 'requests'

// ── Component ──────────────────────────────────────────────────────────────────

export default function JurisdictionData() {
  const [tab, setTab] = useState<Tab>('overview')

  // Overview
  const [overview, setOverview] = useState<DataOverview | null>(null)
  const [loadingOverview, setLoadingOverview] = useState(true)

  // Jurisdictions
  const [search, setSearch] = useState('')
  const [expandedState, setExpandedState] = useState<string | null>(null)
  const [selectedCity, setSelectedCity] = useState<CityEntry | null>(null)
  const [selectedCityState, setSelectedCityState] = useState<string>('')

  // Top metro SSE
  const [metroScanning, setMetroScanning] = useState(false)
  const [metroMessages, setMetroMessages] = useState<string[]>([])

  // Requests
  const [requests, setRequests] = useState<CoverageRequest[]>([])
  const [loadingReqs, setLoadingReqs] = useState(false)

  const fetchOverview = useCallback(async () => {
    setLoadingOverview(true)
    try { setOverview(await api.get<DataOverview>('/admin/jurisdictions/data-overview')) }
    catch { setOverview(null) }
    finally { setLoadingOverview(false) }
  }, [])

  const fetchRequests = useCallback(async () => {
    setLoadingReqs(true)
    try { setRequests(await api.get<CoverageRequest[]>('/admin/jurisdiction-requests?status=pending')) }
    catch { setRequests([]) }
    finally { setLoadingReqs(false) }
  }, [])

  useEffect(() => { fetchOverview() }, [fetchOverview])

  useEffect(() => {
    if (tab === 'requests' && requests.length === 0) fetchRequests()
  }, [tab, fetchRequests, requests.length])

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

  async function processRequest(req: CoverageRequest) {
    await api.post(`/admin/jurisdiction-requests/${req.id}/process`, {
      has_local_ordinance: false,
      county: req.county || null,
      admin_notes: null,
    })
    setRequests((prev) => prev.filter((r) => r.id !== req.id))
  }

  async function dismissRequest(id: string) {
    await api.post(`/admin/jurisdiction-requests/${id}/dismiss`, {})
    setRequests((prev) => prev.filter((r) => r.id !== id))
  }

  const filteredStates = (overview?.states ?? []).filter((s) => {
    if (!search) return true
    const q = search.toLowerCase()
    return s.state.toLowerCase().includes(q) || s.cities.some((c) => c.city.toLowerCase().includes(q))
  })

  const sum = overview?.summary

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">Jurisdiction Data</h1>
          <p className="mt-1 text-sm text-zinc-500">Repository of jurisdiction requirements powering compliance checks.</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 mt-4 mb-5">
        {(['overview', 'jurisdictions', 'requests'] as const).map((t) => (
          <Button key={t} variant={tab === t ? 'secondary' : 'ghost'} size="sm" onClick={() => setTab(t)}>
            {t === 'overview' ? 'Overview' : t === 'jurisdictions' ? 'Jurisdictions' : `Requests${requests.length > 0 ? ` (${requests.length})` : ''}`}
          </Button>
        ))}
      </div>

      {/* ── Overview ── */}
      {tab === 'overview' && (
        <div className="space-y-5">
          {loadingOverview ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : !sum ? (
            <p className="text-sm text-zinc-600">Failed to load data overview.</p>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: 'States', value: sum.total_states },
                  { label: 'Cities', value: sum.total_cities },
                  { label: 'Requirements', value: sum.total_requirements },
                  { label: 'Category Coverage', value: `${sum.category_coverage_pct}%` },
                  { label: 'Tier-1 Data', value: `${sum.tier1_pct}%` },
                  { label: 'Stale (>90d)', value: sum.stale_count },
                ].map((s) => (
                  <div key={s.label} className="border border-zinc-800 rounded-lg px-4 py-3 text-center">
                    <p className="text-xl font-semibold text-zinc-100">{s.value}</p>
                    <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{s.label}</p>
                  </div>
                ))}
              </div>

              <div>
                <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Tier Breakdown</h2>
                <div className="grid grid-cols-3 gap-3">
                  {[1, 2, 3].map((t) => (
                    <div key={t} className="border border-zinc-800 rounded-lg px-4 py-3 text-center">
                      <p className="text-lg font-semibold text-zinc-100">{sum.tier_breakdown[t] ?? 0}</p>
                      <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">
                        Tier {t} {t === 1 ? '(Structured)' : t === 2 ? '(Repository)' : '(Gemini)'}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Data Freshness</h2>
                <div className="grid grid-cols-4 gap-3">
                  {[
                    { label: '< 7 days', value: sum.freshness['7d'] },
                    { label: '< 30 days', value: sum.freshness['30d'] },
                    { label: '< 90 days', value: sum.freshness['90d'] },
                    { label: 'Stale', value: sum.freshness['stale'] },
                  ].map((f) => (
                    <div key={f.label} className="border border-zinc-800 rounded-lg px-3 py-2.5 text-center">
                      <p className="text-lg font-semibold text-zinc-100">{f.value}</p>
                      <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{f.label}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Bulk Research</h2>
                <div className="border border-zinc-800 rounded-lg px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-zinc-200">Top 15 Metros</p>
                      <p className="text-xs text-zinc-500 mt-0.5">Run Gemini research for the 15 highest-priority metro areas.</p>
                    </div>
                    <Button variant="secondary" size="sm" disabled={metroScanning} onClick={startMetroCheck}>
                      {metroScanning ? 'Running...' : 'Run Check'}
                    </Button>
                  </div>
                  {metroScanning && metroMessages.length > 0 && (
                    <div className="mt-3 max-h-32 overflow-y-auto space-y-0.5">
                      {metroMessages.map((msg, i) => (
                        <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Jurisdictions ── */}
      {tab === 'jurisdictions' && (
        <div className="grid grid-cols-5 gap-4">
          {/* Left: states + cities */}
          <div className="col-span-2 space-y-2">
            <Input label="" placeholder="Search state or city..." value={search} onChange={(e) => setSearch(e.target.value)} />

            {loadingOverview ? (
              <p className="text-sm text-zinc-500">Loading...</p>
            ) : filteredStates.length === 0 ? (
              <p className="text-sm text-zinc-600">No jurisdictions found.</p>
            ) : (
              <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60 max-h-[70vh] overflow-y-auto">
                {filteredStates.map((s) => {
                  const isOpen = expandedState === s.state || !!search
                  const citiesToShow = search
                    ? s.cities.filter((c) => c.city.toLowerCase().includes(search.toLowerCase()))
                    : s.cities
                  return (
                    <div key={s.state}>
                      <button
                        type="button"
                        onClick={() => setExpandedState(isOpen && !search ? null : s.state)}
                        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-zinc-800/30 transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-zinc-200">{s.state}</span>
                          <span className="text-[11px] text-zinc-500">{s.city_count} cities</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={`text-[11px] ${s.coverage_pct >= 80 ? 'text-zinc-400' : s.coverage_pct >= 50 ? 'text-amber-400/70' : 'text-red-400/70'}`}>
                            {s.coverage_pct}%
                          </span>
                          <span className="text-zinc-600">{isOpen && !search ? '▾' : '▸'}</span>
                        </div>
                      </button>
                      {isOpen && citiesToShow.map((city) => (
                        <button
                          key={city.id}
                          type="button"
                          onClick={() => { setSelectedCity(city); setSelectedCityState(s.state); setExpandedState(s.state) }}
                          className={`w-full flex items-start justify-between px-4 py-2 text-left border-t border-zinc-800/40 transition-colors border-l-2 ${
                            selectedCity?.id === city.id ? 'bg-zinc-800/60 border-zinc-300' : 'hover:bg-zinc-800/20 border-transparent'
                          }`}
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5">
                              {city.is_stale && <span className="text-[10px] text-amber-400/70">⚠</span>}
                              <span className="text-sm text-zinc-300 truncate">{city.city}</span>
                            </div>
                            <p className="text-[11px] text-zinc-600 mt-0.5">
                              {city.categories_present.length} / {city.categories_present.length + city.categories_missing.length} categories
                            </p>
                          </div>
                          {city.categories_missing.length > 0 && (
                            <span className="text-[11px] text-zinc-600 shrink-0 ml-2">−{city.categories_missing.length}</span>
                          )}
                        </button>
                      ))}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Right: shared detail panel */}
          <div className="col-span-3">
            {!selectedCity ? (
              <div className="flex items-center justify-center h-48 border border-zinc-800 rounded-lg">
                <p className="text-sm text-zinc-600">Select a city to view requirements</p>
              </div>
            ) : (
              <JurisdictionDetailPanel
                id={selectedCity.id}
                city={selectedCity.city}
                state={selectedCityState}
                categoriesMissing={selectedCity.categories_missing}
                onCheckComplete={fetchOverview}
              />
            )}
          </div>
        </div>
      )}

      {/* ── Requests ── */}
      {tab === 'requests' && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Pending Coverage Requests</h2>
            <Button variant="ghost" size="sm" onClick={fetchRequests}>Refresh</Button>
          </div>

          {loadingReqs ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : requests.length === 0 ? (
            <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
              <p className="text-sm text-zinc-600">No pending requests</p>
            </div>
          ) : (
            <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
              {requests.map((req) => (
                <div key={req.id} className="flex items-center gap-4 px-4 py-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-zinc-200">
                      {req.city}, {req.state}
                      {req.county && <span className="text-zinc-500 ml-1.5">({req.county} County)</span>}
                    </p>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-[11px] text-zinc-500">{req.company_name}</span>
                      <span className="text-[11px] text-zinc-600">·</span>
                      <span className="text-[11px] text-zinc-500">{req.employee_count} employees</span>
                      {req.created_at && (
                        <>
                          <span className="text-[11px] text-zinc-600">·</span>
                          <span className="text-[11px] text-zinc-600">{new Date(req.created_at).toLocaleDateString()}</span>
                        </>
                      )}
                    </div>
                    {req.admin_notes && <p className="text-xs text-zinc-600 mt-0.5">{req.admin_notes}</p>}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button variant="secondary" size="sm" onClick={() => processRequest(req)}>Process</Button>
                    <button type="button" onClick={() => dismissRequest(req.id)}
                      className="text-xs text-zinc-600 hover:text-zinc-300 px-2 py-1 transition-colors">
                      Dismiss
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
