import { useEffect, useState, useMemo } from 'react'
import { api } from '../../api/client'
import { HEALTHCARE_SPECIALTIES } from '../../data/industryConstants'

// ── Types ──────────────────────────────────────────────────────────────────────

type CategoryEntry = {
  slug: string
  name: string
  domain: string
  group: string
  industry_tag: string | null
  source: 'base' | 'triggered' | 'specialty' | 'focused'
  triggered_by: string[]
  jurisdiction_count: number
  requirement_count: number
  has_data: boolean
}

type TriggerInfo = {
  key: string
  label: string
  categories: string[]
}

type MatrixResponse = {
  summary: { total: number; with_data: number; missing_data: number }
  industry_profile: { name: string; focused_categories: string[] } | null
  active_triggers: TriggerInfo[]
  categories: CategoryEntry[]
}

const INDUSTRIES = [
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'biotech', label: 'Biotech / Life Sciences' },
  { value: 'restaurant_hospitality', label: 'Restaurant / Hospitality' },
  { value: 'retail', label: 'Retail' },
  { value: 'tech_professional', label: 'Tech / Professional Services' },
  { value: 'fast_food', label: 'Fast Food' },
  { value: 'construction_manufacturing', label: 'Construction / Manufacturing' },
]

const ENTITY_TYPES = [
  'Hospital',
  'FQHC',
  'Critical Access Hospital',
  'Clinic',
  'Nursing Facility',
  'Pharmacy',
  'Behavioral Health',
  'ASC',
  'Home Health',
  'Hospice',
  'Dialysis Center',
  'Lab',
  'Dental',
  'Other',
]

const PAYER_OPTIONS = [
  { value: 'medicare', label: 'Medicare' },
  { value: 'medi_cal', label: 'Medi-Cal' },
  { value: 'medicaid_other', label: 'Medicaid Other' },
  { value: 'commercial', label: 'Commercial' },
  { value: 'tricare', label: 'TRICARE' },
]

const SOURCE_BADGE: Record<string, { bg: string; text: string; border: string }> = {
  base: { bg: 'bg-emerald-900/30', text: 'text-emerald-400', border: 'border-emerald-800/40' },
  triggered: { bg: 'bg-cyan-900/30', text: 'text-cyan-400', border: 'border-cyan-800/40' },
  specialty: { bg: 'bg-purple-900/30', text: 'text-purple-400', border: 'border-purple-800/40' },
  focused: { bg: 'bg-zinc-800', text: 'text-zinc-400', border: 'border-zinc-700' },
}

const GROUP_ORDER = ['Core Labor', 'Supplementary', 'Healthcare', 'Oncology', 'Medical Compliance', 'Life Sciences']

// ── Component ──────────────────────────────────────────────────────────────────

export default function IndustryRequirements() {
  const [industry, setIndustry] = useState('healthcare')
  const [specialties, setSpecialties] = useState<string[]>([])
  const [entityType, setEntityType] = useState('')
  const [payers, setPayers] = useState<string[]>([])
  const [data, setData] = useState<MatrixResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function fetch() {
      setLoading(true)
      try {
        const params = new URLSearchParams({ industry })
        if (industry === 'healthcare') {
          if (specialties.length) params.set('specialties', specialties.join(','))
          if (entityType) params.set('entity_type', entityType)
          if (payers.length) params.set('payer_contracts', payers.join(','))
        }
        const res = await api.get<MatrixResponse>(`/admin/industry-requirements-matrix?${params.toString()}`)
        if (!cancelled) setData(res)
      } catch {
        if (!cancelled) setData(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetch()
    return () => { cancelled = true }
  }, [industry, specialties, entityType, payers])

  function toggleSpecialty(val: string) {
    setSpecialties((prev) => prev.includes(val) ? prev.filter((s) => s !== val) : [...prev, val])
  }

  function togglePayer(val: string) {
    setPayers((prev) => prev.includes(val) ? prev.filter((p) => p !== val) : [...prev, val])
  }

  const grouped = useMemo(() => {
    if (!data) return []
    const map = new Map<string, CategoryEntry[]>()
    for (const cat of data.categories) {
      const g = cat.group || 'Other'
      if (!map.has(g)) map.set(g, [])
      map.get(g)!.push(cat)
    }
    // Sort groups by predefined order, unknown groups at end
    return [...map.entries()].sort(([a], [b]) => {
      const ia = GROUP_ORDER.indexOf(a)
      const ib = GROUP_ORDER.indexOf(b)
      if (ia === -1 && ib === -1) return a.localeCompare(b)
      if (ia === -1) return 1
      if (ib === -1) return -1
      return ia - ib
    })
  }, [data])

  const summary = data?.summary

  return (
    <div className="flex gap-6">
      {/* ── Left Panel ── */}
      <div className="w-64 shrink-0 sticky top-0 self-start space-y-5">
        <div>
          <label className="block text-[10px] uppercase tracking-wide text-zinc-500 font-medium mb-1.5">
            Industry
          </label>
          <select
            value={industry}
            onChange={(e) => {
              setIndustry(e.target.value)
              if (e.target.value !== 'healthcare') {
                setSpecialties([])
                setEntityType('')
                setPayers([])
              }
            }}
            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5"
          >
            {INDUSTRIES.map((ind) => (
              <option key={ind.value} value={ind.value}>{ind.label}</option>
            ))}
          </select>
        </div>

        {industry === 'healthcare' && (
          <>
            {/* Specialties */}
            <div>
              <label className="block text-[10px] uppercase tracking-wide text-zinc-500 font-medium mb-1.5">
                Specialties
              </label>
              <div className="space-y-1 max-h-52 overflow-y-auto pr-1">
                {HEALTHCARE_SPECIALTIES.map((sp) => (
                  <label key={sp.value} className="flex items-center gap-2 text-xs text-zinc-400 hover:text-zinc-200 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={specialties.includes(sp.value)}
                      onChange={() => toggleSpecialty(sp.value)}
                      className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500/30 w-3.5 h-3.5"
                    />
                    {sp.label}
                  </label>
                ))}
              </div>
            </div>

            {/* Entity Type */}
            <div>
              <label className="block text-[10px] uppercase tracking-wide text-zinc-500 font-medium mb-1.5">
                Entity Type
              </label>
              <select
                value={entityType}
                onChange={(e) => setEntityType(e.target.value)}
                className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2.5 py-1.5"
              >
                <option value="">Any</option>
                {ENTITY_TYPES.map((et) => (
                  <option key={et} value={et}>{et}</option>
                ))}
              </select>
            </div>

            {/* Payer Contracts */}
            <div>
              <label className="block text-[10px] uppercase tracking-wide text-zinc-500 font-medium mb-1.5">
                Payer Contracts
              </label>
              <div className="space-y-1">
                {PAYER_OPTIONS.map((p) => (
                  <label key={p.value} className="flex items-center gap-2 text-xs text-zinc-400 hover:text-zinc-200 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={payers.includes(p.value)}
                      onChange={() => togglePayer(p.value)}
                      className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500/30 w-3.5 h-3.5"
                    />
                    {p.label}
                  </label>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      {/* ── Right Panel ── */}
      <div className="flex-1 min-w-0">
        <h1 className="text-2xl font-semibold text-zinc-100">Industry Requirements</h1>
        <p className="mt-1 text-sm text-zinc-500">Category matrix by industry profile</p>

        {loading ? (
          <p className="mt-8 text-sm text-zinc-500">Loading...</p>
        ) : !data ? (
          <p className="mt-8 text-sm text-zinc-600">Failed to load data.</p>
        ) : (
          <>
            {/* Summary bar */}
            {summary && (
              <div className="mt-4 border border-zinc-800 rounded-lg px-4 py-3 flex items-center gap-4">
                <span className="text-sm text-zinc-300">
                  <span className="font-mono font-bold text-zinc-100">{summary.total}</span> categories applicable
                </span>
                <span className="text-zinc-700">|</span>
                <span className="text-sm text-emerald-400">
                  <span className="font-mono font-bold">{summary.with_data}</span> have data
                </span>
                <span className="text-zinc-700">|</span>
                <span className="text-sm text-amber-400">
                  <span className="font-mono font-bold">{summary.missing_data}</span> need research
                </span>
                <div className="flex-1" />
                <div className="w-32 h-2 rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-all"
                    style={{ width: summary.total > 0 ? `${Math.round((summary.with_data / summary.total) * 100)}%` : '0%' }}
                  />
                </div>
              </div>
            )}

            {/* Category table */}
            <div className="mt-4 border border-zinc-800 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-zinc-900/50">
                  <tr>
                    <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide text-zinc-400">Category</th>
                    <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide text-zinc-400">Source</th>
                    <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide text-zinc-400">Triggers</th>
                    <th className="text-left py-2 px-3 font-medium text-[10px] uppercase tracking-wide text-zinc-400">Data Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {grouped.map(([group, cats]) => (
                    <GroupRows key={group} group={group} categories={cats} />
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ── Group rows sub-component ─────────────────────────────────────────────────

function GroupRows({ group, categories }: { group: string; categories: CategoryEntry[] }) {
  return (
    <>
      {/* Group header */}
      <tr>
        <td colSpan={4} className="py-2 px-3 border-b border-zinc-800">
          <span className="text-[10px] uppercase tracking-wide text-zinc-500 font-medium">{group}</span>
        </td>
      </tr>
      {/* Category rows */}
      {categories.map((cat) => {
        const badge = SOURCE_BADGE[cat.source] ?? SOURCE_BADGE.focused
        return (
          <tr key={cat.slug} className={cat.has_data ? 'hover:bg-zinc-800/30' : 'bg-amber-950/10 hover:bg-amber-950/20'}>
            <td className="py-2 px-3 text-zinc-200">{cat.name}</td>
            <td className="py-2 px-3">
              <span className={`inline-block rounded-md px-1.5 py-0.5 text-[10px] font-medium border ${badge.bg} ${badge.text} ${badge.border}`}>
                {cat.source.charAt(0).toUpperCase() + cat.source.slice(1)}
              </span>
            </td>
            <td className="py-2 px-3">
              {cat.triggered_by.length > 0 ? (
                <span className="text-[11px] text-zinc-500">{cat.triggered_by.join(', ')}</span>
              ) : (
                <span className="text-zinc-700">-</span>
              )}
            </td>
            <td className="py-2 px-3">
              {cat.has_data ? (
                <span className="inline-flex items-center gap-1.5 text-[11px] text-zinc-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  {cat.jurisdiction_count} jur &middot; {cat.requirement_count} reqs
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-[11px] text-amber-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                  No data
                </span>
              )}
            </td>
          </tr>
        )
      })}
    </>
  )
}
