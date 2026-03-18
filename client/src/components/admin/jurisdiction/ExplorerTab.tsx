import { useState, useEffect, useMemo } from 'react'
import { Button, Input } from '../../ui'
import { api } from '../../../api/client'
import { CATEGORY_SHORT_LABELS } from '../../../generated/complianceCategories'
import type { FlatCity, CatCoverage, PolicyOverview, PolicyDomainSummary } from './types'
import { fmtDate } from './utils'
import CategoryCoveragePanel from './CategoryCoveragePanel'

type SortKey = 'state' | 'city' | 'coveragePct' | 'gapCount' | 'lastVerified'
type SortDir = 'asc' | 'desc'

type Props = {
  allCities: FlatCity[]
  categoryCoverage: CatCoverage[]
  stateOptions: string[]
  onSelectCity: (city: FlatCity) => void
  selectedCityId: string | null
  onDelete: (id: string) => Promise<void>
}

const PAGE_SIZE = 50

export default function ExplorerTab({
  allCities,
  categoryCoverage,
  stateOptions,
  onSelectCity,
  selectedCityId,
  onDelete,
}: Props) {
  const [search, setSearch] = useState('')
  const [filterState, setFilterState] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterStaleOnly, setFilterStaleOnly] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('gapCount')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [page, setPage] = useState(0)
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Policy overview data for sidebar requirement counts
  const [policySummary, setPolicySummary] = useState<PolicyDomainSummary[] | null>(null)

  useEffect(() => {
    let cancelled = false
    api.get<PolicyOverview>('/admin/jurisdictions/policy-overview')
      .then((data) => { if (!cancelled) setPolicySummary(data.domains) })
      .catch(() => { if (!cancelled) setPolicySummary(null) })
    return () => { cancelled = true }
  }, [])

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      // Smart default: alpha columns asc, numeric columns desc
      const numericKeys: SortKey[] = ['coveragePct', 'gapCount', 'lastVerified']
      setSortDir(numericKeys.includes(key) ? 'desc' : 'asc')
    }
    setPage(0)
  }

  async function handleDeleteCity(cityId: string) {
    setDeleting(true)
    setDeleteError(null)
    try {
      await onDelete(cityId)
      setDeleteConfirm(null)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      if (msg.includes('409') || msg.toLowerCase().includes('linked')) {
        setDeleteError('Cannot delete — linked locations exist')
      } else {
        setDeleteError(msg || 'Delete failed')
      }
    } finally {
      setDeleting(false)
    }
  }

  const filtered = useMemo(() => {
    let rows = allCities
    if (search) {
      const q = search.toLowerCase()
      rows = rows.filter(
        (r) =>
          (r.city || '').toLowerCase().includes(q) ||
          (r.stateName || '').toLowerCase().includes(q)
      )
    }
    if (filterState) rows = rows.filter((r) => r.stateName === filterState)
    if (filterCategory) {
      rows = rows.filter(
        (r) =>
          r.categories_missing.includes(filterCategory) ||
          r.categories_present.includes(filterCategory)
      )
    }
    if (filterStaleOnly) rows = rows.filter((r) => r.is_stale)
    return rows
  }, [allCities, search, filterState, filterCategory, filterStaleOnly])

  const sorted = useMemo(() => {
    const arr = [...filtered]
    const dir = sortDir === 'asc' ? 1 : -1
    arr.sort((a, b) => {
      switch (sortKey) {
        case 'state':
          return dir * a.stateName.localeCompare(b.stateName) || a.city.localeCompare(b.city)
        case 'city':
          return dir * a.city.localeCompare(b.city)
        case 'coveragePct':
          return dir * (a.coveragePct - b.coveragePct)
        case 'gapCount':
          return dir * (a.gapCount - b.gapCount)
        case 'lastVerified': {
          const da = a.last_verified_at ?? ''
          const db = b.last_verified_at ?? ''
          return dir * da.localeCompare(db)
        }
        default:
          return 0
      }
    })
    return arr
  }, [filtered, sortKey, sortDir])

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)
  const paged = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  function sortIcon(key: SortKey) {
    if (sortKey !== key) return ''
    return sortDir === 'asc' ? ' ↑' : ' ↓'
  }

  return (
    <div className="flex gap-4">
      {/* Category sidebar — always visible */}
      <CategoryCoveragePanel
        coverageData={categoryCoverage}
        selectedCategory={filterCategory}
        onSelectCategory={(cat) => {
          setFilterCategory(cat)
          setPage(0)
        }}
        policySummary={policySummary}
      />

      {/* Main table area */}
      <div className="flex-1 min-w-0">
        <div className="border border-zinc-800 rounded-lg">
          {/* Filter bar */}
          <div className="px-3 py-2 border-b border-zinc-800/60 flex flex-wrap items-center gap-2">
            <div className="flex-1 min-w-[140px]">
              <Input
                label=""
                placeholder="Search cities / states..."
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
              {stateOptions.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => { setFilterStaleOnly(!filterStaleOnly); setPage(0) }}
              className={`text-xs px-2.5 py-1 rounded transition-colors ${
                filterStaleOnly
                  ? 'bg-amber-500/20 text-amber-400'
                  : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              Stale only
            </button>
            {filterCategory && (
              <button
                type="button"
                onClick={() => setFilterCategory('')}
                className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition-colors flex items-center gap-1"
              >
                {CATEGORY_SHORT_LABELS[filterCategory] || filterCategory}
                <span>×</span>
              </button>
            )}
            <span className="text-[11px] text-zinc-600 ml-auto">
              {sorted.length} jurisdictions
            </span>
          </div>

          {/* Table */}
          {sorted.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <p className="text-sm text-zinc-600">
                {search || filterState || filterStaleOnly || filterCategory
                  ? 'No cities match these filters.'
                  : 'No jurisdiction data loaded.'}
              </p>
            </div>
          ) : (
            <div className="max-h-[60vh] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="bg-zinc-900/50 text-zinc-400 sticky top-0">
                  <tr>
                    {([
                      ['state', 'ST'],
                      ['city', 'City'],
                      ['coveragePct', 'Coverage'],
                      ['gapCount', 'Gaps'],
                      ['lastVerified', 'Verified'],
                    ] as [SortKey, string][]).map(([key, label]) => (
                      <th
                        key={key}
                        className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide cursor-pointer hover:text-zinc-200 select-none"
                        onClick={() => toggleSort(key)}
                      >
                        {label}{sortIcon(key)}
                      </th>
                    ))}
                    {filterCategory && (
                      <th className="py-2 px-3 font-medium text-[10px] uppercase tracking-wide text-center">
                        {CATEGORY_SHORT_LABELS[filterCategory] || filterCategory}
                      </th>
                    )}
                    <th className="py-2 px-3 w-8" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {paged.map((city, idx) => (
                    <tr
                      key={`${city.id}-${idx}`}
                      className={`cursor-pointer transition-colors ${
                        selectedCityId === city.id
                          ? 'bg-zinc-800/60'
                          : 'hover:bg-zinc-800/30'
                      }`}
                      onClick={() => onSelectCity(city)}
                    >
                      <td className="py-2 px-3 font-mono font-bold text-zinc-200">
                        {city.stateName}
                      </td>
                      <td className={`py-2 px-3 ${city.is_stale ? 'text-amber-300/80' : 'text-zinc-200'}`}>
                        {city.city}
                        {city.is_stale && <span className="text-amber-400/70 ml-1">⚠</span>}
                      </td>
                      <td className="py-2 px-3">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden max-w-[80px]">
                            <div
                              className={`h-full rounded-full ${
                                city.coveragePct >= 80
                                  ? 'bg-emerald-500'
                                  : city.coveragePct >= 50
                                    ? 'bg-amber-400'
                                    : 'bg-red-400'
                              }`}
                              style={{ width: `${city.coveragePct}%` }}
                            />
                          </div>
                          <span className="text-[11px] font-mono text-zinc-500 text-right">
                            {city.presentCount}/{city.totalCount} {city.coveragePct}%
                          </span>
                        </div>
                      </td>
                      <td
                        className={`py-2 px-3 font-mono ${
                          city.totalCount > 0 && city.gapCount >= city.totalCount / 2
                            ? 'text-red-400'
                            : city.gapCount > 0
                              ? 'text-amber-400'
                              : 'text-emerald-400'
                        }`}
                      >
                        {city.gapCount}
                      </td>
                      <td className="py-2 px-3 text-zinc-500 whitespace-nowrap text-[11px]">
                        {fmtDate(city.last_verified_at)}
                      </td>
                      {filterCategory && (
                        <td className="py-2 px-3 text-center">
                          <span className={`inline-block w-2.5 h-2.5 rounded-full ${
                            city.categories_present.includes(filterCategory)
                              ? 'bg-emerald-500'
                              : 'bg-red-400'
                          }`} />
                        </td>
                      )}
                      <td className="py-2 px-3">
                        {deleteConfirm === city.id ? (
                          <div className="flex items-center gap-1 flex-wrap">
                            <button
                              type="button"
                              className="text-[10px] text-red-400 hover:text-red-300 transition-colors"
                              disabled={deleting}
                              onClick={(e) => {
                                e.stopPropagation()
                                handleDeleteCity(city.id)
                              }}
                            >
                              {deleting ? '...' : 'Confirm'}
                            </button>
                            <button
                              type="button"
                              className="text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors"
                              onClick={(e) => {
                                e.stopPropagation()
                                setDeleteConfirm(null)
                                setDeleteError(null)
                              }}
                            >
                              Cancel
                            </button>
                            {deleteError && (
                              <span className="text-[10px] text-red-400/80 block w-full">{deleteError}</span>
                            )}
                          </div>
                        ) : (
                          <button
                            type="button"
                            className="text-[10px] text-zinc-700 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                            onClick={(e) => {
                              e.stopPropagation()
                              setDeleteConfirm(city.id)
                              setDeleteError(null)
                            }}
                            title="Delete"
                          >
                            ✕
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-3 py-2 border-t border-zinc-800/60">
              <span className="text-[11px] text-zinc-600">
                Page {page + 1} of {totalPages}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Prev
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
