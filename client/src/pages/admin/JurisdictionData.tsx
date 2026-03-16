import { useEffect, useState, useCallback } from 'react'
import { api } from '../../api/client'
import { Button, Input } from '../../components/ui'
import { categoryLabel } from '../../types/compliance'
import type { RequirementCategory } from '../../types/compliance'

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

// ── Component ──────────────────────────────────────────────────────────────────

export default function JurisdictionData() {
  const [tab, setTab] = useState<Tab>('coverage')
  const [overview, setOverview] = useState<DataOverview | null>(null)
  const [loadingOverview, setLoadingOverview] = useState(true)
  const [search, setSearch] = useState('')
  const [expandedState, setExpandedState] = useState<string | null>(null)
  const [bookmarks, setBookmarks] = useState<BookmarkedReq[]>([])
  const [loadingBookmarks, setLoadingBookmarks] = useState(false)

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

  // Filter states/cities by search
  const allStates = overview?.states ?? []
  const filteredStates = allStates.filter((s) => {
    if (!search) return true
    const q = search.toLowerCase()
    return s.state.toLowerCase().includes(q) || s.cities.some((c) => c.city.toLowerCase().includes(q))
  })

  // Missing data: cities sorted by most missing categories
  const missingCities: (CityEntry & { stateName: string })[] = []
  for (const st of allStates) {
    for (const city of st.cities) {
      if (city.categories_missing.length > 0) {
        missingCities.push({ ...city, stateName: st.state })
      }
    }
  }
  missingCities.sort((a, b) => b.categories_missing.length - a.categories_missing.length)

  // Preemption rules grouped by state
  const preemptionByState: Record<string, PreemptionRule[]> = {}
  for (const rule of overview?.preemption_rules ?? []) {
    if (!preemptionByState[rule.state]) preemptionByState[rule.state] = []
    preemptionByState[rule.state].push(rule)
  }

  if (loadingOverview && tab !== 'bookmarks') return <p className="text-sm text-zinc-500">Loading...</p>

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">Jurisdiction Data</h1>
          <p className="mt-1 text-sm text-zinc-500">Repository analytics — coverage, data quality, and gaps.</p>
        </div>
        <Button variant="secondary" size="sm" disabled={metroScanning} onClick={startMetroCheck}>
          {metroScanning ? 'Running Top 15...' : 'Run Top 15 Metros'}
        </Button>
      </div>

      {/* Metro SSE progress */}
      {metroScanning && metroMessages.length > 0 && (
        <div className="mt-3 border border-zinc-800 rounded-lg px-3 py-2.5 max-h-28 overflow-y-auto">
          {metroMessages.map((msg, i) => (
            <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-1 mt-4 mb-5">
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

      {/* ── Coverage ── */}
      {tab === 'coverage' && (
        <div className="space-y-3">
          {sum && (
            <div className="grid grid-cols-3 gap-3 mb-4">
              {[
                { label: 'States', value: sum.total_states },
                { label: 'Cities', value: sum.total_cities },
                { label: 'Requirements', value: sum.total_requirements },
              ].map((s) => (
                <div key={s.label} className="border border-zinc-800 rounded-lg px-4 py-3 text-center">
                  <p className="text-xl font-semibold text-zinc-100">{s.value}</p>
                  <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{s.label}</p>
                </div>
              ))}
            </div>
          )}

          <Input label="" placeholder="Search state or city..." value={search} onChange={(e) => setSearch(e.target.value)} />

          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60 max-h-[65vh] overflow-y-auto">
            {filteredStates.map((s) => {
              const isOpen = expandedState === s.state || !!search
              const citiesToShow = search
                ? s.cities.filter((c) => c.city.toLowerCase().includes(search.toLowerCase()))
                : s.cities
              return (
                <div key={s.state}>
                  <button type="button" onClick={() => setExpandedState(isOpen && !search ? null : s.state)}
                    className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-zinc-800/30 transition-colors">
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
                    <div key={city.id} className="px-4 py-2 border-t border-zinc-800/40">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          {city.is_stale && <span className="text-[10px] text-amber-400/70">⚠</span>}
                          <span className="text-sm text-zinc-300">{city.city}</span>
                          <span className="text-[11px] text-zinc-600 ml-1">
                            {city.categories_present.length}/{city.categories_present.length + city.categories_missing.length}
                          </span>
                        </div>
                        {city.last_verified_at && (
                          <span className="text-[11px] text-zinc-600">{new Date(city.last_verified_at).toLocaleDateString()}</span>
                        )}
                      </div>
                      {/* Category dots */}
                      {(city.categories_present.length > 0 || city.categories_missing.length > 0) && (
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {city.categories_present.map((cat) => (
                            <span key={cat} className="text-[10px] text-zinc-500 bg-zinc-800/80 px-1.5 py-0.5 rounded" title={getCategoryLabel(cat)}>
                              {getCategoryLabel(cat)}
                            </span>
                          ))}
                          {city.categories_missing.map((cat) => (
                            <span key={cat} className="text-[10px] text-red-400/60 bg-red-500/10 px-1.5 py-0.5 rounded" title={`Missing: ${getCategoryLabel(cat)}`}>
                              {getCategoryLabel(cat)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Missing Data ── */}
      {tab === 'missing' && (
        <div>
          {missingCities.length === 0 ? (
            <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
              <p className="text-sm text-zinc-600">All cities have complete category coverage.</p>
            </div>
          ) : (
            <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60 max-h-[70vh] overflow-y-auto">
              {missingCities.map((city) => (
                <div key={city.id} className="px-4 py-2.5">
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-zinc-200">{city.city}, {city.stateName}</p>
                    <span className="text-[11px] text-red-400/70">−{city.categories_missing.length} missing</span>
                  </div>
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {city.categories_missing.map((cat) => (
                      <span key={cat} className="text-[10px] text-red-400/60 bg-red-500/10 px-1.5 py-0.5 rounded">
                        {getCategoryLabel(cat)}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Data Quality ── */}
      {tab === 'quality' && sum && (
        <div className="space-y-5">
          {/* Coverage / tier-1 */}
          <div className="grid grid-cols-3 gap-3">
            {[
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

          {/* Tier breakdown */}
          <div>
            <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Tier Breakdown</h2>
            <div className="grid grid-cols-3 gap-3">
              {[
                { tier: 1, label: 'Structured', color: 'text-emerald-400' },
                { tier: 2, label: 'Repository', color: 'text-amber-400' },
                { tier: 3, label: 'Gemini', color: 'text-red-400' },
              ].map(({ tier, label, color }) => (
                <div key={tier} className="border border-zinc-800 rounded-lg px-4 py-3 text-center">
                  <p className={`text-lg font-semibold ${color}`}>{sum.tier_breakdown[tier] ?? 0}</p>
                  <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">Tier {tier} ({label})</p>
                </div>
              ))}
            </div>
          </div>

          {/* Freshness */}
          <div>
            <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-1.5">Data Freshness</h2>
            <div className="grid grid-cols-4 gap-3">
              {[
                { label: '< 7 days', value: sum.freshness['7d'], color: 'text-emerald-400' },
                { label: '< 30 days', value: sum.freshness['30d'], color: 'text-zinc-100' },
                { label: '< 90 days', value: sum.freshness['90d'], color: 'text-amber-400' },
                { label: 'Stale', value: sum.freshness['stale'], color: 'text-red-400' },
              ].map((f) => (
                <div key={f.label} className="border border-zinc-800 rounded-lg px-3 py-2.5 text-center">
                  <p className={`text-lg font-semibold ${f.color}`}>{f.value}</p>
                  <p className="text-[11px] text-zinc-500 uppercase tracking-wide mt-0.5">{f.label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Preemption Rules ── */}
      {tab === 'preemption' && (
        <div>
          {Object.keys(preemptionByState).length === 0 ? (
            <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
              <p className="text-sm text-zinc-600">No preemption rules loaded.</p>
            </div>
          ) : (
            <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60 max-h-[70vh] overflow-y-auto">
              {Object.entries(preemptionByState).sort(([a], [b]) => a.localeCompare(b)).map(([state, rules]) => (
                <div key={state}>
                  <div className="px-4 pt-3 pb-1">
                    <p className="text-xs uppercase tracking-wide text-zinc-400 font-medium">{state}</p>
                  </div>
                  {rules.map((rule, i) => (
                    <div key={i} className="flex items-start gap-3 px-4 py-2 border-t border-zinc-800/30">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-zinc-200">{getCategoryLabel(rule.category)}</p>
                        {rule.notes && <p className="text-xs text-zinc-500 mt-0.5">{rule.notes}</p>}
                      </div>
                      <span className={`text-[11px] shrink-0 px-2 py-0.5 rounded ${
                        rule.allows_local_override
                          ? 'bg-emerald-500/10 text-emerald-400'
                          : 'bg-red-500/10 text-red-400'
                      }`}>
                        {rule.allows_local_override ? 'Local OK' : 'Preempted'}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Bookmarks ── */}
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
