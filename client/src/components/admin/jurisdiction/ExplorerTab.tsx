import { useState, useMemo } from 'react'
import { Button, Input } from '../../ui'
import type { FlatCity } from './types'
import { fmtDate } from './utils'

type SortKey = 'state' | 'city' | 'requirements' | 'gapCount' | 'lastVerified'
type SortDir = 'asc' | 'desc'
type ViewMode = 'cities' | 'states'
type RegionFilter = 'us' | 'international' | 'all'

type Props = {
  allCities: FlatCity[]
  categoryCoverage?: unknown
  stateOptions: string[]
  onSelectCity: (city: FlatCity) => void
  selectedCityId: string | null
  onDelete?: (id: string) => Promise<void>
}

const PAGE_SIZE = 50

export default function ExplorerTab({
  allCities,
  stateOptions,
  onSelectCity,
  selectedCityId,
}: Props) {
  const [search, setSearch] = useState('')
  const [filterState, setFilterState] = useState('')
  const [filterStaleOnly, setFilterStaleOnly] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('requirements')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [page, setPage] = useState(0)
  const [viewMode, setViewMode] = useState<ViewMode>('states')
  const [regionFilter, setRegionFilter] = useState<RegionFilter>('us')

  // Count international jurisdictions for badge
  const intlCount = useMemo(() =>
    allCities.filter(c => c.country_code && c.country_code !== 'US').length,
    [allCities]
  )

  // Filter by region first
  const regionFiltered = useMemo(() => {
    if (regionFilter === 'us') return allCities.filter(c => !c.country_code || c.country_code === 'US')
    if (regionFilter === 'international') return allCities.filter(c => c.country_code && c.country_code !== 'US')
    return allCities
  }, [allCities, regionFilter])

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      const numericKeys: SortKey[] = ['requirements', 'gapCount', 'lastVerified']
      setSortDir(numericKeys.includes(key) ? 'desc' : 'asc')
    }
    setPage(0)
  }

  // ── State-level aggregation ──
  const stateAgg = useMemo(() => {
    const map: Record<string, {
      state: string
      countryCode: string
      cities: FlatCity[]
      totalReqs: number
      cityWithData: number
      cityWithout: number
      lastVerified: string | null
      catPresent: Set<string>
      catMissing: Set<string>
    }> = {}

    for (const c of regionFiltered) {
      const groupKey = regionFilter === 'international' ? `${c.stateName || ''}:${c.country_code || ''}` : c.stateName
      if (!map[groupKey]) {
        map[groupKey] = {
          state: c.stateName || c.country_code || '',
          countryCode: c.country_code || 'US',
          cities: [],
          totalReqs: 0,
          cityWithData: 0,
          cityWithout: 0,
          lastVerified: null,
          catPresent: new Set(),
          catMissing: new Set(),
        }
      }
      const s = map[groupKey]
      s.cities.push(c)
      s.totalReqs += c.presentCount
      if (c.presentCount > 0) s.cityWithData++
      else s.cityWithout++
      if (c.last_verified_at && (!s.lastVerified || c.last_verified_at > s.lastVerified)) {
        s.lastVerified = c.last_verified_at
      }
      for (const cat of c.categories_present) s.catPresent.add(cat)
      for (const cat of c.categories_missing) s.catMissing.add(cat)
    }
    return Object.values(map)
  }, [regionFiltered, regionFilter])

  // ── Filtered & sorted (cities view) ──
  const filtered = useMemo(() => {
    let rows = regionFiltered
    if (search) {
      const q = search.toLowerCase()
      rows = rows.filter(
        (r) => (r.city || '').toLowerCase().includes(q) || (r.stateName || '').toLowerCase().includes(q)
      )
    }
    if (filterState) rows = rows.filter((r) => r.stateName === filterState)
    if (filterStaleOnly) rows = rows.filter((r) => r.is_stale)
    return rows
  }, [regionFiltered, search, filterState, filterStaleOnly])

  const sorted = useMemo(() => {
    const arr = [...filtered]
    const dir = sortDir === 'asc' ? 1 : -1
    arr.sort((a, b) => {
      switch (sortKey) {
        case 'state': return dir * a.stateName.localeCompare(b.stateName) || a.city.localeCompare(b.city)
        case 'city': return dir * a.city.localeCompare(b.city)
        case 'requirements': return dir * (a.presentCount - b.presentCount)
        case 'gapCount': return dir * (a.gapCount - b.gapCount)
        case 'lastVerified': return dir * (a.last_verified_at ?? '').localeCompare(b.last_verified_at ?? '')
        default: return 0
      }
    })
    return arr
  }, [filtered, sortKey, sortDir])

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)
  const paged = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  function sortIcon(key: SortKey) { return sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : '' }

  // ── Filtered states ──
  const filteredStates = useMemo(() => {
    let rows = stateAgg
    if (search) {
      const q = search.toLowerCase()
      rows = rows.filter((s) => s.state.toLowerCase().includes(q))
    }
    if (filterState) rows = rows.filter((s) => s.state === filterState)
    return rows.sort((a, b) => b.totalReqs - a.totalReqs)
  }, [stateAgg, search, filterState])

  return (
    <div className="space-y-0">
      {/* Filter bar */}
      <div className="px-3 py-2 border border-zinc-800 rounded-t-lg flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1 mr-2">
          <button
            onClick={() => { setRegionFilter('us'); setFilterState(''); setPage(0) }}
            className={`text-xs px-2 py-1 rounded ${regionFilter === 'us' ? 'bg-zinc-700 text-zinc-200' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            US
          </button>
          <button
            onClick={() => { setRegionFilter('international'); setFilterState(''); setPage(0) }}
            className={`text-xs px-2 py-1 rounded ${regionFilter === 'international' ? 'bg-zinc-700 text-zinc-200' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            Intl{intlCount > 0 && <span className="ml-1 text-[10px] text-zinc-400">({intlCount})</span>}
          </button>
          <span className="text-zinc-700 mx-0.5">|</span>
          <button
            onClick={() => { setViewMode('states'); setPage(0) }}
            className={`text-xs px-2 py-1 rounded ${viewMode === 'states' ? 'bg-zinc-700 text-zinc-200' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            By State
          </button>
          <button
            onClick={() => { setViewMode('cities'); setPage(0) }}
            className={`text-xs px-2 py-1 rounded ${viewMode === 'cities' ? 'bg-zinc-700 text-zinc-200' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            All Cities
          </button>
        </div>
        <div className="flex-1 min-w-[140px]">
          <Input
            label=""
            placeholder="Search..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0) }}
          />
        </div>
        <select
          value={filterState}
          onChange={(e) => { setFilterState(e.target.value); setPage(0) }}
          className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5"
        >
          <option value="">All States</option>
          {stateOptions.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        {viewMode === 'cities' && (
          <button
            type="button"
            onClick={() => { setFilterStaleOnly(!filterStaleOnly); setPage(0) }}
            className={`text-xs px-2.5 py-1 rounded ${filterStaleOnly ? 'bg-amber-500/20 text-amber-400' : 'text-zinc-500 hover:text-zinc-300'}`}
          >
            Stale only
          </button>
        )}
        <span className="text-[11px] text-zinc-600 ml-auto">
          {viewMode === 'states' ? `${filteredStates.length} states` : `${sorted.length} jurisdictions`}
        </span>
      </div>

      {/* ── States view ── */}
      {viewMode === 'states' && (
        <div className="border border-t-0 border-zinc-800 rounded-b-lg max-h-[65vh] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-zinc-900/50 text-zinc-400 sticky top-0">
              <tr>
                <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wide w-16">State</th>
                <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wide">Cities</th>
                <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wide">Requirements</th>
                <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wide">Categories</th>
                <th className="text-left py-2 px-3 text-[10px] uppercase tracking-wide">Verified</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {filteredStates.map((s) => (
                <StateRow
                  key={s.state}
                  state={s}
                  onSelectCity={onSelectCity}
                  selectedCityId={selectedCityId}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Cities view ── */}
      {viewMode === 'cities' && (
        <div className="border border-t-0 border-zinc-800 rounded-b-lg">
          <div className="max-h-[65vh] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-zinc-900/50 text-zinc-400 sticky top-0">
                <tr>
                  {([
                    ['state', 'ST'],
                    ['city', 'City'],
                    ['requirements', 'Requirements'],
                    ['gapCount', 'Gaps'],
                    ['lastVerified', 'Verified'],
                  ] as [SortKey, string][]).map(([key, label]) => (
                    <th
                      key={key}
                      className="text-left py-2 px-3 text-[10px] uppercase tracking-wide cursor-pointer hover:text-zinc-200 select-none"
                      onClick={() => toggleSort(key)}
                    >
                      {label}{sortIcon(key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {paged.map((city, idx) => {
                  const hasData = city.presentCount > 0
                  return (
                    <tr
                      key={`${city.id}-${idx}`}
                      className={`cursor-pointer transition-colors ${selectedCityId === city.id ? 'bg-zinc-800/60' : 'hover:bg-zinc-800/30'}`}
                      onClick={() => onSelectCity(city)}
                    >
                      <td className="py-2 px-3 font-mono font-bold text-zinc-200 w-16">
                        {city.stateName}
                        {city.country_code && city.country_code !== 'US' && (
                          <span className="text-zinc-500 ml-1 text-[10px]">{city.country_code}</span>
                        )}
                      </td>
                      <td className={`py-2 px-3 ${hasData ? 'text-zinc-200' : 'text-zinc-500 italic'}`}>
                        {city.city || <span className="text-zinc-600">(state level)</span>}
                        {!hasData && city.city && <span className="text-zinc-600 ml-1 text-[10px]">inherits</span>}
                      </td>
                      <td className="py-2 px-3 font-mono text-xs">
                        {hasData ? (
                          <span className="text-zinc-300">{city.presentCount} reqs</span>
                        ) : (
                          <span className="text-zinc-600">0</span>
                        )}
                      </td>
                      <td className={`py-2 px-3 font-mono text-xs ${city.gapCount > 0 ? 'text-amber-400' : 'text-zinc-600'}`}>
                        {city.gapCount > 0 ? city.gapCount : '—'}
                      </td>
                      <td className="py-2 px-3 text-zinc-500 text-[11px]">{fmtDate(city.last_verified_at)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-3 py-2 border-t border-zinc-800/60">
              <span className="text-[11px] text-zinc-600">Page {page + 1} of {totalPages}</span>
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="sm" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Prev</Button>
                <Button variant="ghost" size="sm" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>Next</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── State row with expandable cities ──

function StateRow({
  state,
  onSelectCity,
  selectedCityId,
}: {
  state: {
    state: string
    countryCode: string
    cities: FlatCity[]
    totalReqs: number
    cityWithData: number
    cityWithout: number
    lastVerified: string | null
    catPresent: Set<string>
    catMissing: Set<string>
  }
  onSelectCity: (city: FlatCity) => void
  selectedCityId: string | null
}) {
  const [expanded, setExpanded] = useState(false)
  const citiesWithNames = state.cities.filter((c) => c.city)
  const stateRow = state.cities.find((c) => !c.city)

  return (
    <>
      <tr
        className="cursor-pointer hover:bg-zinc-800/30"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="py-2.5 px-3">
          <span className="font-mono font-bold text-zinc-200">
            {state.state}
            {state.countryCode !== 'US' && <span className="text-zinc-500 ml-1 text-[10px]">{state.countryCode}</span>}
          </span>
          <span className="text-zinc-600 ml-1">{expanded ? '▾' : '▸'}</span>
        </td>
        <td className="py-2.5 px-3 text-zinc-400 text-xs">
          {citiesWithNames.length} {citiesWithNames.length === 1 ? 'city' : 'cities'}
          {state.cityWithout > 0 && (
            <span className="text-zinc-600 ml-1">({state.cityWithout} inheriting)</span>
          )}
        </td>
        <td className="py-2.5 px-3 font-mono text-xs text-zinc-300">
          {state.totalReqs} reqs
        </td>
        <td className="py-2.5 px-3 text-xs">
          <span className="text-zinc-400">{state.catPresent.size}</span>
          <span className="text-zinc-600"> / {state.catPresent.size + state.catMissing.size} categories</span>
        </td>
        <td className="py-2.5 px-3 text-zinc-500 text-[11px]">{fmtDate(state.lastVerified)}</td>
      </tr>
      {expanded && (
        <>
          {/* State-level row */}
          {stateRow && (
            <tr
              className={`bg-zinc-800/20 cursor-pointer hover:bg-zinc-800/40 ${selectedCityId === stateRow.id ? 'bg-zinc-700/40' : ''}`}
              onClick={() => onSelectCity(stateRow)}
            >
              <td className="py-1.5 px-3 pl-8 text-[11px] text-zinc-500" colSpan={1}></td>
              <td className="py-1.5 px-3 text-xs text-amber-400/80">State-level policies</td>
              <td className="py-1.5 px-3 font-mono text-xs text-zinc-400">{stateRow.presentCount} reqs</td>
              <td className="py-1.5 px-3 text-xs text-zinc-500">{stateRow.categories_present.length} categories</td>
              <td className="py-1.5 px-3 text-[11px] text-zinc-500">{fmtDate(stateRow.last_verified_at)}</td>
            </tr>
          )}
          {/* City rows */}
          {citiesWithNames
            .sort((a, b) => b.presentCount - a.presentCount || a.city.localeCompare(b.city))
            .map((city) => (
              <tr
                key={city.id}
                className={`bg-zinc-800/10 cursor-pointer hover:bg-zinc-800/30 ${selectedCityId === city.id ? 'bg-zinc-700/30' : ''}`}
                onClick={() => onSelectCity(city)}
              >
                <td className="py-1.5 px-3 pl-8" />
                <td className="py-1.5 px-3 text-xs text-zinc-300">
                  {city.city}
                  {city.presentCount === 0 && <span className="text-zinc-600 ml-1 text-[10px]">inherits</span>}
                </td>
                <td className="py-1.5 px-3 font-mono text-xs">
                  {city.presentCount > 0 ? (
                    <span className="text-zinc-300">{city.presentCount} reqs</span>
                  ) : (
                    <span className="text-zinc-600">0</span>
                  )}
                </td>
                <td className="py-1.5 px-3 text-xs text-zinc-500">
                  {city.presentCount > 0 ? `${city.categories_present.length} categories` : ''}
                </td>
                <td className="py-1.5 px-3 text-[11px] text-zinc-500">{fmtDate(city.last_verified_at)}</td>
              </tr>
            ))}
        </>
      )}
    </>
  )
}
