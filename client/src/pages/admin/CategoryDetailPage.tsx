import { useState, useEffect, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../../api/client'

interface PolicyKey {
  id: string
  key: string
  name: string
  description: string | null
  state_variance: string
  enforcing_agency: string | null
  base_weight: number
  key_group: string | null
  jurisdiction_count: number
  changed_count: number
  new_count: number
  staleness_level: 'fresh' | 'warning' | 'critical' | 'expired' | 'no_data'
}

interface CategoryDetail {
  slug: string
  name: string
  description: string | null
  domain: string
  group: string
  key_count: number
  requirement_count: number
  state_filter: string | null
  available_states: string[]
  keys: PolicyKey[]
}

const DOMAIN_STYLE: Record<string, string> = {
  healthcare: 'bg-emerald-500/15 text-emerald-400',
  labor: 'bg-blue-500/15 text-blue-400',
  oncology: 'bg-purple-500/15 text-purple-400',
  medical_compliance: 'bg-amber-500/15 text-amber-400',
}

function DomainBadge({ domain }: { domain: string }) {
  const style = DOMAIN_STYLE[domain] ?? 'bg-zinc-700/30 text-zinc-400'
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded font-medium ${style}`}>
      {domain.replace(/_/g, ' ')}
    </span>
  )
}

function StalenessBadge({ level }: { level: string }) {
  switch (level) {
    case 'expired': return <span className="text-red-400 font-bold text-[10px]">EXPIRED</span>
    case 'critical': return <span className="text-red-400 text-[10px]">CRITICAL</span>
    case 'warning': return <span className="text-yellow-400 text-[10px]">STALE</span>
    case 'no_data': return <span className="text-red-300 text-[10px]">NO DATA</span>
    default: return <span className="text-zinc-500 text-[10px]">Fresh</span>
  }
}

function VarianceBadge({ variance }: { variance: string }) {
  const v = variance.toLowerCase()
  if (v === 'high') return <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400">{variance}</span>
  if (v === 'moderate') return <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700/30 text-zinc-300">{variance}</span>
  return <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800/50 text-zinc-500">{variance}</span>
}

export default function CategoryDetailPage() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const [data, setData] = useState<CategoryDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [stateFilter, setStateFilter] = useState('')

  useEffect(() => {
    if (!slug) return
    let cancelled = false
    setLoading(true)
    const qs = stateFilter ? `?state=${stateFilter}` : ''
    api.get<CategoryDetail>(`/admin/jurisdictions/categories/${slug}${qs}`)
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setData(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [slug, stateFilter])

  const filtered = useMemo(() => {
    if (!data) return []
    const q = search.toLowerCase().trim()
    if (!q) return data.keys
    return data.keys.filter(
      (k) => k.key.toLowerCase().includes(q) || k.name.toLowerCase().includes(q)
    )
  }, [data, search])

  if (loading) return <div className="text-zinc-500 py-12 text-center">Loading category...</div>
  if (!data) return <div className="text-zinc-500 py-12 text-center">Category not found.</div>

  return (
    <div className="space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Link to="/admin/jurisdiction-data" className="hover:text-zinc-200 transition-colors">
          &larr; Jurisdiction Data
        </Link>
        <span>/</span>
        <span className="text-zinc-200">{data.name}</span>
      </div>

      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-zinc-100">{data.name}</h1>
          <DomainBadge domain={data.domain} />
        </div>
        {data.description && (
          <p className="text-sm text-zinc-400 mt-2 max-w-2xl">{data.description}</p>
        )}
      </div>

      {/* Stats */}
      <p className="text-xs text-zinc-500">
        {data.key_count} policies &middot; {data.requirement_count.toLocaleString()} jurisdiction entries
        {stateFilter && ` (${stateFilter})`}
      </p>

      {/* Filters */}
      <div className="flex gap-2 items-center">
        <select
          value={stateFilter}
          onChange={(e) => setStateFilter(e.target.value)}
          className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500"
        >
          <option value="">All states</option>
          {data.available_states.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input
          type="text"
          placeholder="Filter policies by name or key..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 max-w-md bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-200 text-sm px-3 py-2 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
        />
      </div>

      {/* Table */}
      <div className="border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-zinc-900/50 text-zinc-400 text-xs uppercase">
            <tr>
              <th className="px-3 py-2 w-52">Key</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2 w-24">Variance</th>
              <th className="px-3 py-2 w-36">Agency</th>
              <th className="px-3 py-2 w-24 text-center">Jurisdictions</th>
              <th className="px-3 py-2 w-24 text-center">Changes</th>
              <th className="px-3 py-2 w-20">Staleness</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/50">
            {filtered.map((k) => (
              <tr
                key={k.id}
                className="cursor-pointer hover:bg-zinc-800/30 transition-colors"
                onClick={() => navigate(`/admin/jurisdiction-data/policy/${k.id}`)}
              >
                <td className="px-3 py-2 font-mono text-xs text-zinc-300">{k.key}</td>
                <td className="px-3 py-2 text-sm text-zinc-200">{k.name}</td>
                <td className="px-3 py-2"><VarianceBadge variance={k.state_variance} /></td>
                <td className="px-3 py-2 text-xs text-zinc-400">{k.enforcing_agency || '\u2014'}</td>
                <td className="px-3 py-2 text-xs text-center font-mono text-zinc-300">{k.jurisdiction_count}</td>
                <td className="px-3 py-2 text-xs text-center">
                  {k.changed_count > 0 || k.new_count > 0 ? (
                    <span className="text-amber-400 font-medium">
                      {k.changed_count > 0 && `${k.changed_count} changed`}
                      {k.changed_count > 0 && k.new_count > 0 && ', '}
                      {k.new_count > 0 && `${k.new_count} new`}
                    </span>
                  ) : (
                    <span className="text-zinc-600">\u2014</span>
                  )}
                </td>
                <td className="px-3 py-2"><StalenessBadge level={k.staleness_level} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <p className="text-sm text-zinc-600 text-center py-6">
            {search ? `No policies match "${search}"` : 'No policies in this category.'}
          </p>
        )}
      </div>
    </div>
  )
}
