import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'

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

type ScopedTo = {
  state: string
  city: string | null
  city_found: boolean | null
  jurisdictions_in_chain: number
}

type MatrixResponse = {
  summary: { total: number; with_data: number; missing_data: number }
  industry_profile: { name: string; focused_categories: string[] } | null
  /** Non-null when coverage is scoped to an establishment's jurisdiction chain. */
  scoped_to: ScopedTo | null
  active_triggers: TriggerInfo[]
  categories: CategoryEntry[]
}

type Specialty = {
  industry_tag: string
  slug: string
  label: string
  /** 0 means ticking it selects nothing — the state the old hardcoded list hid. */
  category_count: number
  discovered_by: string
  confirmed_at: string | null
}

type ProposedCategory = {
  key: string
  label?: string
  description?: string
  authority_sources?: string[]
  is_existing?: boolean
}

type DiscoverResponse = {
  industry: string
  slug: string
  label: string
  industry_tag: string
  categories: ProposedCategory[]
  research_context: string
  already_exists: boolean
}

// Values are the CANONICAL industry slugs produced by `_resolve_industry` on the
// backend. They previously used their own vocabulary (`construction_manufacturing`,
// `tech_professional`, …), which matched neither `industry_compliance_profiles.name`
// nor `compliance_categories.industry_tag` — so those industries rendered an empty
// matrix.
const INDUSTRIES = [
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'biotech', label: 'Biotech / Life Sciences' },
  { value: 'hospitality', label: 'Restaurant / Hospitality' },
  { value: 'retail', label: 'Retail' },
  { value: 'technology', label: 'Tech / Professional Services' },
  { value: 'fast food', label: 'Fast Food' },
  { value: 'manufacturing', label: 'Construction / Manufacturing' },
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

const GROUP_ORDER = ['Core Labor', 'Supplementary', 'Healthcare', 'Oncology', 'Medical Compliance', 'Life Sciences', 'Manufacturing']

// ── Specialty discovery ────────────────────────────────────────────────────────

/**
 * Review step between Gemini's proposal and the DB write. Confirming creates
 * `compliance_categories` rows with **zero requirements behind them** — that
 * `0 jur · 0 reqs` state in the matrix is the scope output, i.e. the worklist of
 * what to research and codify next.
 */
function SpecialtyReviewModal({
  proposal,
  industry,
  onCancel,
  onConfirmed,
}: {
  proposal: DiscoverResponse
  industry: string
  onCancel: () => void
  onConfirmed: (slug: string) => void
}) {
  const novel = useMemo(() => proposal.categories.filter((c) => !c.is_existing), [proposal])
  const [selected, setSelected] = useState<Set<string>>(() => new Set(novel.map((c) => c.key)))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const existing = proposal.categories.filter((c) => c.is_existing)

  const toggle = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const confirm = async () => {
    setSaving(true)
    setError(null)
    try {
      await api.post(`/admin/industries/${encodeURIComponent(industry)}/specialties/confirm`, {
        slug: proposal.slug,
        label: proposal.label,
        research_context: proposal.research_context,
        categories: novel.filter((c) => selected.has(c.key)),
      })
      onConfirmed(proposal.slug)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to confirm specialty')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6">
      <div className="w-full max-w-2xl max-h-[85vh] overflow-y-auto bg-zinc-950 border border-zinc-800 rounded-xl p-5">
        <h2 className="text-base font-semibold text-zinc-100">
          Add specialty: {proposal.label}
        </h2>
        <p className="text-xs text-zinc-500 mt-1">
          Confirming records the <strong className="text-zinc-400">scope</strong> — these categories,
          with no regulations behind them yet. They will appear in the matrix as{' '}
          <span className="text-amber-400">need research</span>, which is the list to codify.
        </p>
        {proposal.already_exists && (
          <p className="text-xs text-amber-400 mt-2">
            This specialty already exists — confirming updates it and adds any new categories.
          </p>
        )}

        <div className="mt-4 space-y-2">
          {novel.map((cat) => (
            <label
              key={cat.key}
              className="flex gap-2.5 items-start border border-zinc-800 rounded-lg p-2.5 cursor-pointer hover:border-zinc-700"
            >
              <input
                type="checkbox"
                checked={selected.has(cat.key)}
                onChange={() => toggle(cat.key)}
                className="mt-0.5 rounded border-zinc-600 bg-zinc-800 text-emerald-500 w-3.5 h-3.5"
              />
              <div className="min-w-0">
                <p className="text-sm text-zinc-200">{cat.label || cat.key}</p>
                <p className="text-[11px] text-zinc-600 font-mono">{cat.key}</p>
                {cat.description && (
                  <p className="text-xs text-zinc-500 mt-1">{cat.description}</p>
                )}
                {!!cat.authority_sources?.length && (
                  <p className="text-[11px] text-zinc-600 mt-1">
                    Authorities: {cat.authority_sources.join(', ')}
                  </p>
                )}
              </div>
            </label>
          ))}
          {!novel.length && (
            <p className="text-sm text-zinc-500">
              No new categories proposed — this specialty is fully covered by the existing baseline.
            </p>
          )}
        </div>

        {!!existing.length && (
          <details className="mt-3 text-xs">
            <summary className="cursor-pointer text-zinc-500">
              {existing.length} already in the baseline — will not be re-created
            </summary>
            <ul className="mt-1.5 space-y-0.5 text-zinc-600 font-mono">
              {existing.map((c) => <li key={c.key}>{c.key}</li>)}
            </ul>
          </details>
        )}

        {error && <p className="text-xs text-red-400 mt-3">{error}</p>}

        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-xs rounded-lg border border-zinc-700 text-zinc-400 hover:text-zinc-200"
          >
            Cancel
          </button>
          <button
            onClick={confirm}
            disabled={saving}
            className="px-3 py-1.5 text-xs rounded-lg bg-emerald-600/90 hover:bg-emerald-600 text-white disabled:opacity-50"
          >
            {saving ? 'Saving…' : `Confirm scope (${selected.size})`}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function IndustryRequirements() {
  const [industry, setIndustry] = useState('healthcare')
  const [specialties, setSpecialties] = useState<string[]>([])
  const [entityType, setEntityType] = useState('')
  const [payers, setPayers] = useState<string[]>([])
  const [data, setData] = useState<MatrixResponse | null>(null)
  const [loading, setLoading] = useState(true)

  // Specialties are DB-derived. The old hardcoded list offered seven healthcare
  // checkboxes with no categories behind them, which silently did nothing.
  const [available, setAvailable] = useState<Specialty[]>([])
  const [newSpecialty, setNewSpecialty] = useState('')
  const [discovering, setDiscovering] = useState(false)
  const [proposal, setProposal] = useState<DiscoverResponse | null>(null)
  const [specialtyError, setSpecialtyError] = useState<string | null>(null)
  const [matrixNonce, setMatrixNonce] = useState(0)

  // Location scopes coverage to a real establishment's jurisdiction chain
  // (city ∪ county ∪ state ∪ federal) instead of "does anyone, anywhere, have data".
  const [state, setState] = useState('')
  const [city, setCity] = useState('')
  const [onlyGaps, setOnlyGaps] = useState(false)

  const loadSpecialties = useCallback(async () => {
    try {
      const res = await api.get<{ specialties: Specialty[] }>(
        `/admin/industries/${encodeURIComponent(industry)}/specialties`,
      )
      setAvailable(res.specialties)
    } catch {
      setAvailable([])
    }
  }, [industry])

  useEffect(() => {
    setSpecialties([])
    setSpecialtyError(null)
    loadSpecialties()
  }, [industry, loadSpecialties])

  useEffect(() => {
    let cancelled = false
    async function fetch() {
      setLoading(true)
      try {
        const params = new URLSearchParams({ industry })
        // Specialties apply to every industry (manufacturing has `quality`,
        // `procurement`); only entity types and payers are healthcare-shaped.
        if (specialties.length) params.set('specialties', specialties.join(','))
        if (industry === 'healthcare') {
          if (entityType) params.set('entity_type', entityType)
          if (payers.length) params.set('payer_contracts', payers.join(','))
        }
        if (state.trim()) {
          params.set('state', state.trim().toUpperCase())
          if (city.trim()) params.set('city', city.trim())
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
  }, [industry, specialties, entityType, payers, state, city, matrixNonce])

  const discoverSpecialty = async () => {
    const name = newSpecialty.trim()
    if (!name || discovering) return
    setDiscovering(true)
    setSpecialtyError(null)
    try {
      const res = await api.post<DiscoverResponse>(
        `/admin/industries/${encodeURIComponent(industry)}/specialties/discover`,
        { name },
      )
      setProposal(res)
    } catch (e) {
      setSpecialtyError(e instanceof Error ? e.message : 'Discovery failed')
    } finally {
      setDiscovering(false)
    }
  }

  const onSpecialtyConfirmed = async (slug: string) => {
    setProposal(null)
    setNewSpecialty('')
    await loadSpecialties()
    setSpecialties((prev) => (prev.includes(slug) ? prev : [...prev, slug]))
    setMatrixNonce((n) => n + 1)
  }

  function toggleSpecialty(val: string) {
    setSpecialties((prev) => prev.includes(val) ? prev.filter((s) => s !== val) : [...prev, val])
  }

  function togglePayer(val: string) {
    setPayers((prev) => prev.includes(val) ? prev.filter((p) => p !== val) : [...prev, val])
  }

  const grouped = useMemo(() => {
    if (!data) return []
    const map = new Map<string, CategoryEntry[]>()
    // With `onlyGaps`, the table becomes the codify worklist: the categories this
    // industry is liable for that have no requirement in this jurisdiction chain.
    const rows = onlyGaps ? data.categories.filter((c) => !c.has_data) : data.categories
    for (const cat of rows) {
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
  }, [data, onlyGaps])

  const summary = data?.summary

  return (
    <div className="flex gap-6">
      {proposal && (
        <SpecialtyReviewModal
          proposal={proposal}
          industry={industry}
          onCancel={() => setProposal(null)}
          onConfirmed={onSpecialtyConfirmed}
        />
      )}

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

        {/* Location — scopes coverage to a real establishment's chain */}
        <div>
          <label className="block text-[10px] uppercase tracking-wide text-zinc-500 font-medium mb-1.5">
            Location
          </label>
          <div className="flex gap-1">
            <input
              value={state}
              onChange={(e) => setState(e.target.value.toUpperCase().slice(0, 2))}
              placeholder="ST"
              className="w-14 bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2 py-1.5 placeholder:text-zinc-600"
            />
            <input
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="City (optional)"
              disabled={!state.trim()}
              className="flex-1 min-w-0 bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2 py-1.5 placeholder:text-zinc-600 disabled:opacity-50"
            />
          </div>
          {data?.scoped_to ? (
            <p className="text-[11px] text-zinc-500 mt-1">
              Coverage across {data.scoped_to.jurisdictions_in_chain} jurisdiction
              {data.scoped_to.jurisdictions_in_chain === 1 ? '' : 's'} (city ∪ county ∪ state ∪ federal)
            </p>
          ) : (
            <p className="text-[11px] text-zinc-600 mt-1">
              Unset — counts are global, not for any one establishment.
            </p>
          )}
          {data?.scoped_to?.city_found === false && (
            <p className="text-[11px] text-amber-400 mt-1">
              No jurisdiction record for “{data.scoped_to.city}” — showing state + federal only.
            </p>
          )}
        </div>

        {/* Specialties — DB-derived, extensible */}
        <div>
          <label className="block text-[10px] uppercase tracking-wide text-zinc-500 font-medium mb-1.5">
            Specialties
          </label>
          <div className="space-y-1 max-h-52 overflow-y-auto pr-1">
            {available.map((sp) => (
              <label
                key={sp.slug}
                className="flex items-center gap-2 text-xs text-zinc-400 hover:text-zinc-200 cursor-pointer"
                title={`${sp.category_count} categor${sp.category_count === 1 ? 'y' : 'ies'}`}
              >
                <input
                  type="checkbox"
                  checked={specialties.includes(sp.slug)}
                  onChange={() => toggleSpecialty(sp.slug)}
                  className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500/30 w-3.5 h-3.5"
                />
                <span className="flex-1 truncate">{sp.label}</span>
                <span className={sp.category_count ? 'text-zinc-600' : 'text-amber-500/70'}>
                  {sp.category_count}
                </span>
              </label>
            ))}
            {!available.length && (
              <p className="text-xs text-zinc-600">None yet — add one below.</p>
            )}
          </div>

          <div className="flex gap-1 mt-2">
            <input
              value={newSpecialty}
              onChange={(e) => setNewSpecialty(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') discoverSpecialty() }}
              placeholder="+ Add specialty…"
              disabled={discovering}
              className="flex-1 min-w-0 bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-xs px-2 py-1.5 placeholder:text-zinc-600 disabled:opacity-50"
            />
            <button
              onClick={discoverSpecialty}
              disabled={discovering || !newSpecialty.trim()}
              className="px-2 py-1.5 text-xs rounded-lg border border-zinc-700 text-zinc-400 hover:text-zinc-200 disabled:opacity-40"
            >
              {discovering ? '…' : '↵'}
            </button>
          </div>
          {discovering && (
            <p className="text-[11px] text-zinc-500 mt-1">Deriving regulatory scope…</p>
          )}
          {specialtyError && <p className="text-[11px] text-red-400 mt-1">{specialtyError}</p>}
        </div>

        {industry === 'healthcare' && (
          <>
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
                  <span className="font-mono font-bold">{summary.with_data}</span> codified
                  {data.scoped_to && ` for ${[data.scoped_to.city, data.scoped_to.state].filter(Boolean).join(', ')}`}
                </span>
                <span className="text-zinc-700">|</span>
                <button
                  onClick={() => setOnlyGaps((v) => !v)}
                  disabled={!summary.missing_data}
                  title="Show only the categories with no requirement in this jurisdiction chain"
                  className={`text-sm rounded-md px-2 py-0.5 border transition-colors disabled:opacity-50 ${
                    onlyGaps
                      ? 'border-amber-500/60 bg-amber-500/10 text-amber-300'
                      : 'border-transparent text-amber-400 hover:border-zinc-700'
                  }`}
                >
                  <span className="font-mono font-bold">{summary.missing_data}</span> to codify
                </button>
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
