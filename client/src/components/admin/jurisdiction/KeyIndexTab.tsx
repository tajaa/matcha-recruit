import { AdminInput, AdminSelect, AdminTable } from '../AdminUI'
import { useState, useMemo } from 'react'
import { useAsync } from '../../../hooks/useAsync'
import { Link } from 'react-router-dom'
import { fetchKeyCoverage } from '../../../api/compliance'
import type { CategoryKeyCoverage, RegulationKeyCoverage } from '../../../api/compliance'
import { CATEGORY_LABELS } from '../../../generated/complianceCategories'

type GroupFilter = 'all' | 'labor' | 'healthcare' | 'oncology' | 'medical_compliance' | 'supplementary'
type StalenessFilter = 'all' | 'fresh' | 'warning' | 'critical' | 'expired' | 'no_data'

function stalenessLabel(level: string) {
  switch (level) {
    case 'expired': return <span className="text-red-400 font-bold">EXPIRED</span>
    case 'critical': return <span className="text-red-400">CRITICAL</span>
    case 'warning': return <span className="text-yellow-400">STALE</span>
    case 'no_data': return <span className="text-red-300">NO DATA</span>
    default: return <span className="text-zinc-500">Fresh</span>
  }
}

function KeyRow({ k, expanded, onToggle }: { k: RegulationKeyCoverage; expanded: boolean; onToggle: () => void }) {
  const isMissing = k.jurisdiction_count === 0
  return (
    <>
      <tr
        className={`border-b border-zinc-800/50 cursor-pointer hover:bg-zinc-800/30 ${isMissing ? 'text-red-400' : ''}`}
        onClick={onToggle}
      >
        <td className="font-mono">
          <Link to={`/admin/jurisdiction-data/policy/${k.id}`} className="hover:text-emerald-400" onClick={e => e.stopPropagation()}>{k.key}</Link>
        </td>
        <td >
          <Link to={`/admin/jurisdiction-data/policy/${k.id}`} className="hover:text-emerald-400" onClick={e => e.stopPropagation()}>{k.name}</Link>
        </td>
        <td className="text-zinc-400">{k.enforcing_agency || '—'}</td>
        <td className="text-center">{k.base_weight > 1 ? <span className="text-purple-300">{k.base_weight}x</span> : '1x'}</td>
        <td className="text-zinc-500">{k.key_group || '—'}</td>
        <td className="text-center font-mono">{k.jurisdiction_count}</td>
        <td >{stalenessLabel(k.staleness_level)}</td>
        <td className="text-zinc-500 font-mono">{k.newest_value || '—'}</td>
      </tr>
      {expanded && (
        <tr className="bg-zinc-800/20">
          <td colSpan={8} className="text-zinc-400">
            <div className="flex gap-6">
              <div><strong>State variance:</strong> {k.state_variance}</div>
              <div><strong>Best tier:</strong> T{k.best_tier || 0}</div>
              {k.days_since_verified != null && <div><strong>Last verified:</strong> {k.days_since_verified}d ago</div>}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export default function KeyIndexTab() {
  const { data, loading } = useAsync(() => fetchKeyCoverage(), [], null)
  const [search, setSearch] = useState('')
  const [groupFilter, setGroupFilter] = useState<GroupFilter>('all')
  const [stalenessFilter, setStalenessFilter] = useState<StalenessFilter>('all')
  const [expandedKey, setExpandedKey] = useState<string | null>(null)
  const [collapsedCats, setCollapsedCats] = useState<Set<string>>(new Set())

  const filtered = useMemo(() => {
    if (!data) return []
    return data.by_category
      .filter(cat => groupFilter === 'all' || cat.group === groupFilter)
      .map(cat => ({
        ...cat,
        keys: cat.keys.filter(k => {
          if (stalenessFilter !== 'all' && k.staleness_level !== stalenessFilter) return false
          if (search) {
            const q = search.toLowerCase()
            return k.key.includes(q) || k.name.toLowerCase().includes(q) || (k.enforcing_agency || '').toLowerCase().includes(q)
          }
          return true
        }),
      }))
      .filter(cat => cat.keys.length > 0)
  }, [data, search, groupFilter, stalenessFilter])

  const toggleCat = (cat: string) => {
    setCollapsedCats(prev => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  if (loading) return <div className="text-zinc-500 py-12 text-center">Loading key index...</div>
  if (!data) return <div className="text-zinc-500 py-12 text-center">Failed to load</div>

  const totalKeys = filtered.reduce((s, c) => s + c.keys.length, 0)

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <AdminInput
          type="text"
          placeholder="Search keys, names, agencies..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-72"
        />
        <AdminSelect value={groupFilter} onChange={e => setGroupFilter(e.target.value as GroupFilter)} >
          <option value="all">All Groups</option>
          <option value="labor">Labor</option>
          <option value="healthcare">Healthcare</option>
          <option value="oncology">Oncology</option>
          <option value="medical_compliance">Medical Compliance</option>
          <option value="supplementary">Supplementary</option>
        </AdminSelect>
        <AdminSelect value={stalenessFilter} onChange={e => setStalenessFilter(e.target.value as StalenessFilter)} >
          <option value="all">All Staleness</option>
          <option value="fresh">Fresh</option>
          <option value="warning">Stale (Warning)</option>
          <option value="critical">Critical</option>
          <option value="expired">Expired</option>
          <option value="no_data">No Data</option>
        </AdminSelect>
        <span className="text-xs text-zinc-500 ml-auto">{totalKeys} keys shown</span>
      </div>

      {/* Table */}
      <AdminTable>
        <thead >
          <tr>
            <th className="w-48">Key</th>
            <th >Name</th>
            <th className="w-40">Agency</th>
            <th className="w-16 text-center">Wt</th>
            <th className="w-32">Group</th>
            <th className="w-20 text-center">Jur.</th>
            <th className="w-20">Stale</th>
            <th className="w-28">Value</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map(cat => (
            <CategorySection
              key={cat.category}
              cat={cat}
              collapsed={collapsedCats.has(cat.category)}
              onToggle={() => toggleCat(cat.category)}
              expandedKey={expandedKey}
              onKeyToggle={k => setExpandedKey(expandedKey === k ? null : k)}
            />
          ))}
        </tbody>
      </AdminTable>
    </div>
  )
}

function CategorySection({
  cat, collapsed, onToggle, expandedKey, onKeyToggle,
}: {
  cat: CategoryKeyCoverage
  collapsed: boolean
  onToggle: () => void
  expandedKey: string | null
  onKeyToggle: (k: string) => void
}) {
  const label = CATEGORY_LABELS[cat.category] || cat.category
  const missingCount = cat.expected - cat.present
  return (
    <>
      <tr
        className="bg-zinc-800/40 cursor-pointer hover:bg-zinc-800/60 border-b border-zinc-700/30"
        onClick={onToggle}
      >
        <td colSpan={8} >
          <div className="flex items-center gap-3 text-sm">
            <span className="text-zinc-500">{collapsed ? '▸' : '▾'}</span>
            <Link to={`/admin/jurisdiction-data/category/${cat.category}`} className="font-medium text-zinc-200 hover:text-emerald-400" onClick={e => e.stopPropagation()}>{label}</Link>
            <span className="text-xs text-zinc-500">{cat.category}</span>
            <span className="text-xs font-mono text-zinc-400">{cat.present}/{cat.expected}</span>
            {missingCount > 0 && (
              <span className="text-xs text-red-400">{missingCount} missing</span>
            )}
            {cat.partial_groups.length > 0 && (
              <span className="text-xs text-yellow-400">{cat.partial_groups.length} partial groups</span>
            )}
          </div>
        </td>
      </tr>
      {!collapsed && cat.keys.map(k => (
        <KeyRow
          key={k.key}
          k={k}
          expanded={expandedKey === k.key}
          onToggle={() => onKeyToggle(k.key)}
        />
      ))}
    </>
  )
}
