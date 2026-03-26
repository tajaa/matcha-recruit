import { useEffect, useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../api/client'
import { fmtDate } from './utils'
import type {
  PolicyOverview,
  PolicyCategoryDetail,
  PolicyCategorySummary,
  PolicyDomainSummary,
} from './types'

// ── Tier badge colors ──────────────────────────────────────────────────────────

const TIER_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  tier_1_government: { bg: 'bg-emerald-500/15', text: 'text-emerald-400', label: 'Tier 1' },
  tier_2_official_secondary: { bg: 'bg-amber-400/15', text: 'text-amber-400', label: 'Tier 2' },
  tier_3_aggregator: { bg: 'bg-red-400/15', text: 'text-red-400', label: 'Tier 3' },
}

function TierBadge({ tier }: { tier: string }) {
  const s = TIER_STYLE[tier] ?? TIER_STYLE.tier_3_aggregator
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${s.bg} ${s.text}`}>
      {s.label}
    </span>
  )
}

// ── Mini tier bar for category cards ───────────────────────────────────────────

function TierMiniBar({ breakdown }: { breakdown: PolicyCategorySummary['tier_breakdown'] }) {
  const total = breakdown.tier_1_government + breakdown.tier_2_official_secondary + breakdown.tier_3_aggregator
  if (total === 0) return null
  const pct1 = (breakdown.tier_1_government / total) * 100
  const pct2 = (breakdown.tier_2_official_secondary / total) * 100
  return (
    <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden flex">
      {pct1 > 0 && <div className="bg-emerald-500 h-full" style={{ width: `${pct1}%` }} />}
      {pct2 > 0 && <div className="bg-amber-400 h-full" style={{ width: `${pct2}%` }} />}
      <div className="bg-red-400 h-full flex-1" />
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function PolicyBrowserTab() {
  const [overview, setOverview] = useState<PolicyOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [collapsedDomains, setCollapsedDomains] = useState<Set<string>>(new Set())

  // Drill-down state
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [detail, setDetail] = useState<PolicyCategoryDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [detailSearch, setDetailSearch] = useState('')
  const [sortCol, setSortCol] = useState<'state' | 'title' | 'last_verified_at'>('state')
  const [sortAsc, setSortAsc] = useState(true)

  // Fetch overview
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.get<PolicyOverview>('/admin/jurisdictions/policy-overview')
      .then((data) => { if (!cancelled) setOverview(data) })
      .catch(() => { if (!cancelled) setOverview(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  // Fetch detail when category selected
  useEffect(() => {
    if (!selectedCategory) { setDetail(null); return }
    let cancelled = false
    setLoadingDetail(true)
    setDetailSearch('')
    api.get<PolicyCategoryDetail>(`/admin/jurisdictions/policy-overview?category=${selectedCategory}`)
      .then((data) => { if (!cancelled) setDetail(data) })
      .catch(() => { if (!cancelled) setDetail(null) })
      .finally(() => { if (!cancelled) setLoadingDetail(false) })
    return () => { cancelled = true }
  }, [selectedCategory])

  // Filter domains/categories by search
  const filteredDomains = useMemo<PolicyDomainSummary[]>(() => {
    if (!overview) return []
    const q = search.toLowerCase().trim()
    if (!q) return overview.domains
    return overview.domains
      .map((d) => ({
        ...d,
        categories: d.categories.filter(
          (c) => c.name.toLowerCase().includes(q) || c.slug.includes(q) || d.label.toLowerCase().includes(q)
        ),
      }))
      .filter((d) => d.categories.length > 0)
  }, [overview, search])

  // Filter & sort detail requirements
  const filteredReqs = useMemo(() => {
    if (!detail) return []
    let reqs = detail.requirements
    const q = detailSearch.toLowerCase().trim()
    if (q) {
      reqs = reqs.filter(
        (r) =>
          r.title.toLowerCase().includes(q) ||
          r.state.toLowerCase().includes(q) ||
          (r.city ?? '').toLowerCase().includes(q) ||
          (r.current_value ?? '').toLowerCase().includes(q)
      )
    }
    return [...reqs].sort((a, b) => {
      let cmp = 0
      if (sortCol === 'state') cmp = a.state.localeCompare(b.state) || (a.city ?? '').localeCompare(b.city ?? '')
      else if (sortCol === 'title') cmp = a.title.localeCompare(b.title)
      else if (sortCol === 'last_verified_at') cmp = (a.last_verified_at ?? '').localeCompare(b.last_verified_at ?? '')
      return sortAsc ? cmp : -cmp
    })
  }, [detail, detailSearch, sortCol, sortAsc])

  function toggleDomain(domain: string) {
    setCollapsedDomains((prev) => {
      const next = new Set(prev)
      if (next.has(domain)) next.delete(domain)
      else next.add(domain)
      return next
    })
  }

  function handleSort(col: typeof sortCol) {
    if (sortCol === col) setSortAsc(!sortAsc)
    else { setSortCol(col); setSortAsc(true) }
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading policy data...</p>
  if (!overview) return <p className="text-sm text-zinc-600">Failed to load policy data.</p>

  const sum = overview.summary

  return (
    <div className="space-y-5">
      {/* KPI row */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'Requirements', value: sum.total_requirements.toLocaleString() },
          { label: 'Categories', value: sum.total_categories_with_data.toString() },
          { label: 'Domains', value: sum.total_domains.toString() },
          { label: 'Jurisdictions', value: sum.total_jurisdictions.toLocaleString() },
        ].map((s) => (
          <div key={s.label} className="border border-zinc-800 rounded-lg px-3 py-3">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium">{s.label}</p>
            <p className="text-2xl font-bold tracking-tight mt-0.5 text-zinc-100">{s.value}</p>
          </div>
        ))}
      </div>

      {/* Search */}
      <input
        type="text"
        placeholder="Search categories..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-200 text-sm px-3 py-2 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
      />

      {/* Domain sections */}
      {filteredDomains.map((domain) => (
        <div key={domain.domain}>
          <button
            type="button"
            onClick={() => toggleDomain(domain.domain)}
            className="flex items-center gap-2 w-full text-left group"
          >
            <svg
              className={`w-3.5 h-3.5 text-zinc-500 transition-transform ${collapsedDomains.has(domain.domain) ? '' : 'rotate-90'}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
            <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide group-hover:text-zinc-200 transition-colors">
              {domain.label}
            </h2>
            <span className="text-[10px] text-zinc-600 font-mono">
              {domain.category_count} categories · {domain.requirement_count.toLocaleString()} reqs
            </span>
          </button>

          {!collapsedDomains.has(domain.domain) && (
            <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {domain.categories.map((cat) => (
                <button
                  key={cat.slug}
                  type="button"
                  onClick={() => setSelectedCategory(cat.slug === selectedCategory ? null : cat.slug)}
                  className={`text-left border rounded-lg px-3 py-2.5 transition-colors ${
                    selectedCategory === cat.slug
                      ? 'border-blue-500/50 bg-blue-500/5'
                      : 'border-zinc-800 hover:border-zinc-700 hover:bg-zinc-800/30'
                  }`}
                >
                  <p className="text-sm text-zinc-200 font-medium">{cat.name}</p>
                  <div className="flex items-center gap-3 mt-1.5 text-[11px] text-zinc-500">
                    <span>{cat.requirement_count} reqs</span>
                    <span>{cat.jurisdiction_count} jurisdictions</span>
                    {cat.latest_verified && (
                      <span className="text-zinc-600">verified {fmtDate(cat.latest_verified)}</span>
                    )}
                    <Link
                      to={`/admin/jurisdiction-data/category/${cat.slug}`}
                      className="text-emerald-500 hover:text-emerald-400 ml-auto"
                      onClick={e => e.stopPropagation()}
                    >
                      View details →
                    </Link>
                  </div>
                  <div className="mt-2">
                    <TierMiniBar breakdown={cat.tier_breakdown} />
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      ))}

      {filteredDomains.length === 0 && (
        <p className="text-sm text-zinc-600 text-center py-6">No categories match "{search}"</p>
      )}

      {/* Detail panel */}
      {selectedCategory && (
        <div className="border border-zinc-800 rounded-lg overflow-hidden">
          <div className="px-4 py-3 bg-zinc-900/50 flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-zinc-200">
                {detail?.category.name ?? selectedCategory}
              </p>
              {detail && (
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  {detail.requirements.length} requirements across jurisdictions
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => setSelectedCategory(null)}
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Close
            </button>
          </div>

          {loadingDetail ? (
            <p className="text-sm text-zinc-500 px-4 py-6">Loading requirements...</p>
          ) : detail && detail.requirements.length > 0 ? (
            <>
              {detail.requirements.length > 10 && (
                <div className="px-4 pt-3">
                  <input
                    type="text"
                    placeholder="Search requirements..."
                    value={detailSearch}
                    onChange={(e) => setDetailSearch(e.target.value)}
                    className="w-full bg-zinc-900 border border-zinc-700 rounded text-zinc-300 text-xs px-2.5 py-1.5 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
                  />
                </div>
              )}
              <div className="max-h-[60vh] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-zinc-900/50 text-zinc-400 sticky top-0">
                    <tr>
                      {([
                        { key: 'state' as const, label: 'State' },
                        { key: null, label: 'City' },
                        { key: null, label: 'Level' },
                        { key: 'title' as const, label: 'Title' },
                        { key: null, label: 'Value' },
                        { key: null, label: 'Tier' },
                        { key: 'last_verified_at' as const, label: 'Verified' },
                      ]).map((col, i) => (
                        <th
                          key={i}
                          className={`text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide ${col.key ? 'cursor-pointer hover:text-zinc-200 select-none' : ''}`}
                          onClick={col.key ? () => handleSort(col.key!) : undefined}
                        >
                          {col.label}
                          {col.key && sortCol === col.key && (
                            <span className="ml-0.5">{sortAsc ? '↑' : '↓'}</span>
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800">
                    {filteredReqs.map((r) => (
                      <tr key={r.id} className="hover:bg-zinc-800/30">
                        <td className="py-2 px-3 font-mono font-bold text-zinc-200 whitespace-nowrap">{r.state}</td>
                        <td className="py-2 px-3 text-zinc-400 text-xs">{r.city ?? '—'}</td>
                        <td className="py-2 px-3 text-zinc-500 text-xs">{r.jurisdiction_level}</td>
                        <td className="py-2 px-3 text-zinc-200 max-w-xs truncate" title={r.title}>{r.title}</td>
                        <td className="py-2 px-3 text-zinc-400 text-xs whitespace-nowrap">{r.current_value ?? '—'}</td>
                        <td className="py-2 px-3"><TierBadge tier={r.source_tier} /></td>
                        <td className="py-2 px-3 text-zinc-500 text-[11px] whitespace-nowrap">{fmtDate(r.last_verified_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {detailSearch && filteredReqs.length === 0 && (
                <p className="text-xs text-zinc-600 text-center py-4">No requirements match "{detailSearch}"</p>
              )}
            </>
          ) : (
            <p className="text-sm text-zinc-600 px-4 py-6">No requirements found for this category.</p>
          )}
        </div>
      )}
    </div>
  )
}
