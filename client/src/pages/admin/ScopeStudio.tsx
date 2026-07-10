/**
 * Scope Studio — the unified specialization-scope surface.
 *
 * Merges /admin/industry-requirements (the coverage matrix + specialty
 * derive/confirm) and /admin/specialization-research (the research run) into one
 * coordinate-driven page, and shows the new scope-registry engine's grounded
 * resolution alongside the category-group matrix.
 *
 * One coordinate (industry × jurisdiction × headcount) drives three panels:
 *   1. Coverage matrix — applicable / codified / to-codify (category groups).
 *   2. Registry resolution — the authority-anchored engine's codified keys +
 *      the uncodified fetch queue (the grounded worklist).
 *   3. Derive a specialty → confirm scope → research the gap inline (SSE).
 *
 * Reuses the two source pages' proven blocks (SpecialtyReviewModal, the matrix
 * rows, the SSE read loop). See ONE_COMPLIANCE_SYSTEM.md for the architecture.
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Microscope, Loader2, Check } from 'lucide-react'
import { api, ensureFreshToken } from '../../api/client'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

// Research model tier (ported from the retired Specialization Research page).
const MODEL_LABELS: Record<string, { label: string; model: string; color: string }> = {
  light: { label: 'Light', model: 'Gemini 3 Flash', color: 'bg-blue-900/50 text-blue-300' },
  heavy: { label: 'Pro', model: 'Gemini 3.1 Pro', color: 'bg-purple-900/50 text-purple-300' },
}

// Canonical industry slugs — what the matrix and /scope-registry/resolve expect.
const INDUSTRIES = [
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'biotech', label: 'Biotech / Life Sciences' },
  { value: 'hospitality', label: 'Restaurant / Hospitality' },
  { value: 'retail', label: 'Retail' },
  { value: 'technology', label: 'Tech / Professional Services' },
  { value: 'fast food', label: 'Fast Food' },
  { value: 'manufacturing', label: 'Construction / Manufacturing' },
  { value: 'warehousing', label: 'Warehousing & Storage' },
]

const HEADCOUNTS = ['', '1-10', '11-50', '51-100', '101-500', '501-1000', '1001+']

// Rough midpoint headcount so conditional strata (FMLA ≥ 50) evaluate in the
// resolve preview. The registry keys on employee_count.
const HEADCOUNT_MIDPOINT: Record<string, number> = {
  '1-10': 5, '11-50': 30, '51-100': 75, '101-500': 300, '501-1000': 750, '1001+': 1500,
}

const GROUP_ORDER = [
  'Core Labor', 'Supplementary', 'Healthcare', 'Oncology',
  'Medical Compliance', 'Life Sciences', 'Manufacturing',
]

const SOURCE_BADGE: Record<string, string> = {
  base: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  triggered: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  specialty: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
  focused: 'bg-zinc-500/15 text-zinc-300 border-zinc-500/30',
}

// ── Types (mirror the matrix + scope-registry endpoints) ─────────────────────

type CategoryEntry = {
  slug: string
  name: string
  group: string
  source: 'base' | 'triggered' | 'specialty' | 'focused'
  triggered_by: string[]
  jurisdiction_count: number
  requirement_count: number
  has_data: boolean
}

type MatrixResponse = {
  summary: { total: number; with_data: number; missing_data: number }
  scoped_to: { state: string; city: string | null; city_found: boolean | null } | null
  categories: CategoryEntry[]
}

type Specialty = {
  industry_tag: string
  slug: string
  label: string
  category_count: number
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
}

type ResolveItem = {
  citation: string
  heading: string | null
  regulation_key: string | null
  disposition: string
}

type ResolveResult = {
  coordinate: { category_chain: string[]; state_found: boolean; city_found: boolean }
  codified: ResolveItem[]
  uncodified: ResolveItem[]
  counts: {
    applicable: number; codified: number; uncodified: number
    provisional: number; conditional_skipped: number
  }
  unmodeled_coordinates: { kind: string; value: string; note: string }[]
}

// ── Labor scope (jurisdiction-first, industry-agnostic) ──────────────────────

type LaborScopeRequirement = {
  title?: string | null
  current_value?: string | null
  source_url?: string | null
  source_name?: string | null
  jurisdiction_name?: string | null
  jurisdiction_level?: string | null
  last_verified_at?: string | null
  codified_at?: string | null
  codify_source?: string | null
}

type LaborScopeLevel = {
  codified: {
    citation: string; heading: string | null; regulation_key: string | null
    requirement?: LaborScopeRequirement | null
  }[]
  uncodified: { citation: string; heading: string | null; regulation_key: string | null }[]
  counts: { codified: number; uncodified: number; provisional: number }
}

type LaborExhaustiveness = {
  basis: 'enumerated' | 'curated' | 'none'
  note: string
  indexes: {
    slug: string; name: string; source_type: string | null
    enumerable: boolean; item_count: number; unclassified_count: number
  }[]
  enumeration?: { indexes: number; enumerated: number; classified: number; unclassified: number }
}

type LaborScopeResponse = {
  coordinate: { state: string | null; city: string | null; state_found: boolean; city_found: boolean }
  core: {
    items: { category: string; key: string; present: boolean; level: string | null }[]
    present: number; total: number; complete: boolean
  }
  registry: {
    levels: { federal: LaborScopeLevel; state: LaborScopeLevel; city: LaborScopeLevel }
    skipped: { category_specific: number; conditional: number }
  }
  exhaustiveness: { federal: LaborExhaustiveness; state: LaborExhaustiveness; city: LaborExhaustiveness }
}

const LEVEL_LABELS: [keyof LaborScopeResponse['registry']['levels'], string][] = [
  ['federal', 'Federal'], ['state', 'State'], ['city', 'City / Local'],
]

// ── Specialty derive/confirm modal (from IndustryRequirements, verbatim shape) ─

function SpecialtyReviewModal({
  proposal, industry, onCancel, onConfirmed,
}: {
  proposal: DiscoverResponse
  industry: string
  onCancel: () => void
  onConfirmed: (slug: string) => void
}) {
  const novel = proposal.categories.filter((c) => !c.is_existing)
  const existing = proposal.categories.filter((c) => c.is_existing)
  const [selected, setSelected] = useState<Set<string>>(new Set(novel.map((c) => c.key)))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggle = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
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
      setError(e instanceof Error ? e.message : 'Failed to confirm scope')
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 p-6">
        <h3 className="text-lg font-semibold text-zinc-100">
          Confirm scope for {proposal.label}
        </h3>
        <p className="mt-1 text-sm text-zinc-400">
          Confirming records these as applicable compliance categories with no
          regulations behind them yet — they appear in the matrix as “to codify”.
        </p>

        <div className="mt-4 space-y-2">
          {novel.map((c) => (
            <label
              key={c.key}
              className="flex cursor-pointer gap-3 rounded border border-zinc-800 bg-zinc-950/50 p-3 hover:border-zinc-600"
            >
              <input
                type="checkbox"
                checked={selected.has(c.key)}
                onChange={() => toggle(c.key)}
                className="mt-1"
              />
              <div className="min-w-0">
                <div className="text-sm font-medium text-zinc-200">{c.label || c.key}</div>
                <div className="font-mono text-xs text-zinc-500">{c.key}</div>
                {c.description && <div className="mt-1 text-xs text-zinc-400">{c.description}</div>}
                {c.authority_sources?.length ? (
                  <div className="mt-1 text-xs text-zinc-500">
                    Authorities: {c.authority_sources.join(', ')}
                  </div>
                ) : null}
              </div>
            </label>
          ))}
        </div>

        {existing.length > 0 && (
          <details className="mt-3 text-xs text-zinc-500">
            <summary className="cursor-pointer">{existing.length} already in the baseline</summary>
            <div className="mt-1 space-y-0.5">
              {existing.map((c) => (
                <div key={c.key} className="font-mono">{c.key}</div>
              ))}
            </div>
          </details>
        )}

        {error && <div className="mt-3 text-sm text-red-400">{error}</div>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            onClick={confirm}
            disabled={saving || selected.size === 0}
            className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            {saving ? 'Saving…' : `Confirm scope (${selected.size})`}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── The page ─────────────────────────────────────────────────────────────────

export default function ScopeStudio() {
  const [industry, setIndustry] = useState('healthcare')
  const [state, setState] = useState('')
  const [city, setCity] = useState('')
  const [headcount, setHeadcount] = useState('')
  const [specialties, setSpecialties] = useState<string[]>([])
  const [available, setAvailable] = useState<Specialty[]>([])

  const [matrix, setMatrix] = useState<MatrixResponse | null>(null)
  const [matrixLoading, setMatrixLoading] = useState(true)
  const [onlyGaps, setOnlyGaps] = useState(false)
  const [matrixNonce, setMatrixNonce] = useState(0)

  const [resolveResult, setResolveResult] = useState<ResolveResult | null>(null)
  const [resolveError, setResolveError] = useState<string | null>(null)

  const [laborScope, setLaborScope] = useState<LaborScopeResponse | null>(null)
  const [laborError, setLaborError] = useState<string | null>(null)

  const [newSpecialty, setNewSpecialty] = useState('')
  const [discovering, setDiscovering] = useState(false)
  const [proposal, setProposal] = useState<DiscoverResponse | null>(null)
  const [specialtyError, setSpecialtyError] = useState<string | null>(null)
  // A derived specialty's categories, kept so "research the gap" sends real
  // category keys (the research run researches exactly `categories`).
  const [researchTarget, setResearchTarget] =
    useState<{ label: string; industry_tag: string; categories: string[] } | null>(null)

  // Research (SSE) — reused from SpecializationResearch. `source` distinguishes
  // which flow started the run so only that panel shows the progress strip.
  const [research, setResearch] = useState<{
    source: 'gap' | 'queue'
    running: boolean; message: string; completed: number; total: number; error: string | null
  } | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Research model tier (light/heavy) — display-only status, ported from the
  // retired Specialization Research page.
  const [modelMode, setModelMode] = useState<string>('light')
  useEffect(() => {
    api.get<{ jurisdiction_research_model_mode?: string }>('/admin/platform-settings')
      .then((d) => setModelMode(d.jurisdiction_research_model_mode || 'light'))
      .catch(() => {})
  }, [])

  // ── Specialties for the current industry ──
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
    loadSpecialties()
  }, [loadSpecialties])

  // ── Coverage matrix ──
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setMatrixLoading(true)
      try {
        const params = new URLSearchParams({ industry })
        if (specialties.length) params.set('specialties', specialties.join(','))
        if (state.trim()) {
          params.set('state', state.trim().toUpperCase())
          if (city.trim()) params.set('city', city.trim())
        }
        const res = await api.get<MatrixResponse>(
          `/admin/industry-requirements-matrix?${params.toString()}`,
        )
        if (!cancelled) setMatrix(res)
      } catch {
        if (!cancelled) setMatrix(null)
      } finally {
        if (!cancelled) setMatrixLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [industry, specialties, state, city, matrixNonce])

  // ── Registry resolution (the grounded engine view) ──
  useEffect(() => {
    let cancelled = false
    if (!state.trim()) {
      setResolveResult(null)
      setResolveError(null)
      return
    }
    ;(async () => {
      try {
        const params = new URLSearchParams({ category: industry, state: state.trim().toUpperCase() })
        if (city.trim()) params.set('city', city.trim())
        if (headcount && HEADCOUNT_MIDPOINT[headcount]) {
          params.set('headcount', String(HEADCOUNT_MIDPOINT[headcount]))
        }
        const res = await api.get<ResolveResult>(`/admin/scope-registry/resolve?${params.toString()}`)
        if (!cancelled) {
          setResolveResult(res)
          setResolveError(null)
        }
      } catch (e) {
        if (!cancelled) {
          setResolveResult(null)
          setResolveError(e instanceof Error ? e.message : 'Resolution failed')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [industry, state, city, headcount, matrixNonce])

  // ── Labor scope (jurisdiction-only; NOT keyed on industry/headcount) ──
  // Federal labor law is state-independent, so this loads with no state too —
  // the federal column always resolves; state/city fill in once a state is set.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const params = new URLSearchParams()
        if (state.trim()) {
          params.set('state', state.trim().toUpperCase())
          if (city.trim()) params.set('city', city.trim())
        }
        const qs = params.toString()
        const res = await api.get<LaborScopeResponse>(
          `/admin/scope-registry/labor-scope${qs ? `?${qs}` : ''}`,
        )
        if (!cancelled) {
          setLaborScope(res)
          setLaborError(null)
        }
      } catch (e) {
        if (!cancelled) {
          setLaborScope(null)
          setLaborError(e instanceof Error ? e.message : 'Labor scope failed')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [state, city, matrixNonce])

  const grouped = useMemo(() => {
    if (!matrix) return [] as [string, CategoryEntry[]][]
    const cats = onlyGaps ? matrix.categories.filter((c) => !c.has_data) : matrix.categories
    const buckets = new Map<string, CategoryEntry[]>()
    for (const c of cats) {
      const g = c.group || 'Other'
      if (!buckets.has(g)) buckets.set(g, [])
      buckets.get(g)!.push(c)
    }
    return [...buckets.entries()].sort(
      (a, b) => GROUP_ORDER.indexOf(a[0]) - GROUP_ORDER.indexOf(b[0]),
    )
  }, [matrix, onlyGaps])

  const toggleSpecialty = (slug: string) =>
    setSpecialties((prev) =>
      prev.includes(slug) ? prev.filter((s) => s !== slug) : [...prev, slug],
    )

  const discoverSpecialty = async () => {
    const name = newSpecialty.trim()
    if (!name) return
    setDiscovering(true)
    setSpecialtyError(null)
    try {
      const res = await api.post<DiscoverResponse>(
        `/admin/industries/${encodeURIComponent(industry)}/specialties/discover`,
        { name },
      )
      setProposal(res)
      setResearchTarget({
        label: res.label,
        industry_tag: res.industry_tag,
        categories: res.categories.map((c) => c.key),
      })
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

  // ── Research the gap inline (reuses the SSE read loop) ──
  // Shared SSE research streamer — both the specialty-gap run and the
  // fetch-queue run POST a body and consume the same event types.
  const streamResearch = async (source: 'gap' | 'queue', url: string, body: unknown) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setResearch({ source, running: true, message: 'Starting research…', completed: 0, total: 0, error: null })

    try {
      const token = await ensureFreshToken()
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      })
      if (!res.ok) {
        const errBody = await res.json().catch(() => null)
        throw new Error(errBody?.detail ?? `Request failed (${res.status})`)
      }

      const reader = res.body?.getReader()
      if (!reader) throw new Error('No response body')
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6).trim()
          if (!payload || payload === 'DONE' || payload === '[DONE]') continue
          let event: {
            type: string; message?: string; jurisdiction?: string
            progress?: number; total?: number; summary?: { total_requirements?: number }
          }
          try {
            event = JSON.parse(payload)
          } catch {
            continue
          }
          if (event.type === 'status') {
            setResearch((r) => (r ? { ...r, message: event.message ?? '' } : r))
          } else if (event.type === 'researching') {
            setResearch((r) =>
              r
                ? {
                    ...r,
                    message: `Researching ${event.jurisdiction}… (${event.progress}/${event.total})`,
                    total: event.total ?? r.total,
                  }
                : r,
            )
          } else if (event.type === 'jurisdiction_complete') {
            setResearch((r) => (r ? { ...r, completed: r.completed + 1 } : r))
          } else if (event.type === 'completed') {
            setResearch((r) =>
              r
                ? {
                    ...r,
                    running: false,
                    message: `Found ${event.summary?.total_requirements ?? 0} requirements`,
                  }
                : r,
            )
            setMatrixNonce((n) => n + 1)
          } else if (event.type === 'error') {
            setResearch((r) => (r ? { ...r, running: false, error: event.message ?? 'Research failed' } : r))
          }
        }
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return
      setResearch({
        source, running: false, message: '', completed: 0, total: 0,
        error: e instanceof Error ? e.message : 'Research failed',
      })
    }
  }

  // Researches the derived specialty's OWN categories (from researchTarget) —
  // the run tags everything it writes with industry_tag, so passing another
  // specialty's categories would mis-tag them. Empty categories research
  // nothing, so a target is required.
  const researchTargetGap = () => {
    if (!researchTarget || researchTarget.categories.length === 0) return
    if (!state.trim()) {
      setResearch({ source: 'gap', running: false, message: '', completed: 0, total: 0, error: 'Set a state first.' })
      return
    }
    const cities = city.trim() ? [{ city: city.trim(), state: state.trim().toUpperCase() }] : []
    streamResearch('gap', `${BASE}/admin/specialization-research/run`, {
      specialization: researchTarget.label,
      parent_industry: industry,
      industry_tag: researchTarget.industry_tag,
      categories: researchTarget.categories,
      states: [state.trim().toUpperCase()],
      cities,
      industry_context: '',
    })
  }

  // Researches the chain's fetch queue directly — the keyed-but-uncodified
  // obligations the Labor scope panel shows — then reconciles so they codify.
  const researchFetchQueue = () => {
    streamResearch('queue', `${BASE}/admin/scope-registry/fetch-queue/research`, {
      state: state.trim() ? state.trim().toUpperCase() : null,
      city: city.trim() || null,
    })
  }

  useEffect(() => () => abortRef.current?.abort(), [])

  return (
    <div className="mx-auto max-w-7xl p-6 text-zinc-200">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Scope Studio</h1>
          <p className="mt-1 text-sm text-zinc-400">
            One coordinate → coverage matrix, the registry’s grounded resolution, and
            derive → confirm → research the gap.
          </p>
        </div>
        {(() => {
          const info = MODEL_LABELS[modelMode] || MODEL_LABELS.light
          return (
            <div className={`shrink-0 rounded-md px-2.5 py-1 text-xs font-medium ${info.color}`}
                 title={`Research model: ${info.model}`}>
              {info.label}
              <span className="ml-1.5 hidden opacity-60 sm:inline">{info.model}</span>
            </div>
          )
        })()}
      </div>

      {/* Coordinate bar */}
      <div className="mb-6 flex flex-wrap items-end gap-4 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <label className="text-xs text-zinc-400">
          Industry
          <select
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            className="mt-1 block rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100"
          >
            {INDUSTRIES.map((i) => (
              <option key={i.value} value={i.value}>{i.label}</option>
            ))}
          </select>
        </label>
        <label className="text-xs text-zinc-400">
          State
          <input
            value={state}
            onChange={(e) => setState(e.target.value)}
            placeholder="CA"
            maxLength={2}
            className="mt-1 block w-20 rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm uppercase text-zinc-100"
          />
        </label>
        <label className="text-xs text-zinc-400">
          City (optional)
          <input
            value={city}
            onChange={(e) => setCity(e.target.value)}
            placeholder="Los Angeles"
            className="mt-1 block w-40 rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100"
          />
        </label>
        <label className="text-xs text-zinc-400">
          Headcount
          <select
            value={headcount}
            onChange={(e) => setHeadcount(e.target.value)}
            className="mt-1 block rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100"
          >
            {HEADCOUNTS.map((h) => (
              <option key={h} value={h}>{h || 'Any'}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Coverage matrix (2 cols) */}
        <div className="lg:col-span-2">
          {/* Specialties */}
          <div className="mb-4 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="mb-2 text-sm font-medium text-zinc-300">Specialties</div>
            <div className="flex flex-wrap gap-2">
              {available.map((s) => (
                <button
                  key={s.slug}
                  onClick={() => toggleSpecialty(s.slug)}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    specialties.includes(s.slug)
                      ? 'border-purple-500/50 bg-purple-500/15 text-purple-200'
                      : 'border-zinc-700 text-zinc-400 hover:border-zinc-500'
                  }`}
                  title={s.category_count === 0 ? 'No categories behind this specialty yet' : ''}
                >
                  {s.label}
                  <span className={s.category_count === 0 ? 'ml-1 text-amber-400' : 'ml-1 text-zinc-500'}>
                    {s.category_count}
                  </span>
                </button>
              ))}
            </div>
            <div className="mt-3 flex gap-2">
              <input
                value={newSpecialty}
                onChange={(e) => setNewSpecialty(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && discoverSpecialty()}
                placeholder="Add a specialty (e.g. ophthalmology)…"
                className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100"
              />
              <button
                onClick={discoverSpecialty}
                disabled={discovering || !newSpecialty.trim()}
                className="rounded bg-zinc-700 px-3 py-2 text-sm text-zinc-100 hover:bg-zinc-600 disabled:opacity-50"
              >
                {discovering ? '…' : 'Derive ↵'}
              </button>
            </div>
            {specialtyError && <div className="mt-2 text-xs text-red-400">{specialtyError}</div>}
          </div>

          {/* Summary + matrix */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            {matrix && (
              <div className="mb-3 flex items-center gap-4 text-sm">
                <span className="text-zinc-300">{matrix.summary.total} applicable</span>
                <span className="text-emerald-400">{matrix.summary.with_data} codified</span>
                <button
                  onClick={() => setOnlyGaps((v) => !v)}
                  className={`rounded px-2 py-0.5 text-xs ${
                    onlyGaps ? 'bg-amber-500/20 text-amber-300' : 'text-amber-400 hover:bg-amber-500/10'
                  }`}
                >
                  {matrix.summary.missing_data} to codify
                </button>
                {matrix.scoped_to?.city && matrix.scoped_to.city_found === false && (
                  <span className="text-xs text-amber-400">city not found — state ∪ federal</span>
                )}
              </div>
            )}
            {matrixLoading ? (
              <div className="py-8 text-center text-sm text-zinc-500">Loading…</div>
            ) : !matrix ? (
              <div className="py-8 text-center text-sm text-zinc-500">No matrix data.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs uppercase text-zinc-500">
                    <tr>
                      <th className="py-2">Category</th>
                      <th className="py-2">Source</th>
                      <th className="py-2">Data</th>
                    </tr>
                  </thead>
                  <tbody>
                    {grouped.map(([group, cats]) => (
                      <Fragment key={group}>
                        <tr>
                          <td colSpan={3} className="pt-3 text-xs font-semibold uppercase text-zinc-500">
                            {group}
                          </td>
                        </tr>
                        {cats.map((c) => (
                          <tr key={c.slug} className={!c.has_data ? 'bg-amber-950/10' : ''}>
                            <td className="py-1.5 text-zinc-200">{c.name}</td>
                            <td className="py-1.5">
                              <span
                                className={`rounded border px-1.5 py-0.5 text-[10px] ${
                                  SOURCE_BADGE[c.source] || SOURCE_BADGE.focused
                                }`}
                              >
                                {c.source}
                              </span>
                            </td>
                            <td className="py-1.5 text-xs">
                              {c.has_data ? (
                                <span className="text-emerald-400">
                                  {c.jurisdiction_count} jur · {c.requirement_count} reqs
                                </span>
                              ) : (
                                <span className="text-amber-400">No data</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Registry resolution + research (1 col) */}
        <div className="space-y-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="mb-2 text-sm font-medium text-zinc-300">Registry resolution</div>
            {!state.trim() ? (
              <div className="text-xs text-zinc-500">Set a state to resolve scope.</div>
            ) : resolveError ? (
              <div className="text-xs text-red-400">{resolveError}</div>
            ) : !resolveResult ? (
              <div className="text-xs text-zinc-500">Resolving…</div>
            ) : (
              <>
                <div className="flex gap-3 text-xs">
                  <span className="text-zinc-300">{resolveResult.counts.applicable} applicable</span>
                  <span className="text-emerald-400">{resolveResult.counts.codified} codified</span>
                  <span className="text-amber-400">{resolveResult.counts.uncodified} to codify</span>
                </div>
                {resolveResult.counts.provisional > 0 && (
                  <div className="mt-1 text-[11px] text-zinc-500">
                    {resolveResult.counts.provisional} provisional (unconfirmed, excluded from scope)
                  </div>
                )}
                {resolveResult.uncodified.length > 0 && (
                  <div className="mt-3">
                    <div className="text-[11px] uppercase text-zinc-500">Fetch queue</div>
                    <ul className="mt-1 space-y-1">
                      {resolveResult.uncodified.slice(0, 12).map((it) => (
                        <li key={it.citation} className="text-xs text-zinc-400">
                          <span className="font-mono text-zinc-300">{it.citation}</span>
                          {it.heading ? ` — ${it.heading}` : ''}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {resolveResult.unmodeled_coordinates.length > 0 && (
                  <div className="mt-3 rounded border border-amber-500/30 bg-amber-500/5 p-2 text-[11px] text-amber-300">
                    {resolveResult.unmodeled_coordinates.map((u, i) => (
                      <div key={i}>{u.kind}: {u.note}</div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Research the gap */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="mb-2 text-sm font-medium text-zinc-300">Research the gap</div>
            {researchTarget && researchTarget.categories.length > 0 ? (
              <button
                onClick={researchTargetGap}
                disabled={research?.running || !state.trim()}
                className="flex w-full items-center justify-between rounded border border-zinc-800 px-3 py-2 text-left text-xs text-zinc-200 hover:border-zinc-600 disabled:opacity-50"
              >
                <span>
                  Research {researchTarget.label} — {researchTarget.categories.length} categories
                  {!state.trim() && <span className="text-amber-400"> (set a state)</span>}
                </span>
                <Microscope className="h-3.5 w-3.5 text-zinc-500" />
              </button>
            ) : (
              <div className="text-xs text-zinc-500">
                Derive a specialty above, then research its categories here.
              </div>
            )}
            {research && research.source === 'gap' && (
              <div className="mt-3 rounded border border-zinc-800 bg-zinc-950/50 p-3 text-xs">
                {research.error ? (
                  <div className="text-red-400">{research.error}</div>
                ) : (
                  <div className="flex items-center gap-2 text-zinc-300">
                    {research.running ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Check className="h-3.5 w-3.5 text-emerald-400" />
                    )}
                    <span>{research.message}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Labor scope — the authoritative "what must we fetch" view (jurisdiction-first) */}
      <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="mb-1 flex items-baseline justify-between">
          <div className="text-sm font-medium text-zinc-300">
            Labor scope{laborScope?.coordinate.state ? ` — ${laborScope.coordinate.state}${laborScope.coordinate.city ? `, ${laborScope.coordinate.city}` : ''}` : ' — Federal'}
          </div>
          <div className="flex items-center gap-3">
            {laborScope
              && (['federal', 'state', 'city'] as const).some((l) => laborScope.registry.levels[l].counts.uncodified > 0) && (
              <button
                onClick={researchFetchQueue}
                disabled={research?.running}
                className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-200 hover:border-amber-400 disabled:opacity-50"
              >
                Research these · codify
              </button>
            )}
            <div className="text-[11px] text-zinc-500">generic employer · federal + state + city</div>
          </div>
        </div>
        {research && research.source === 'queue' && (
          <div className="mb-3 rounded border border-zinc-800 bg-zinc-950/50 p-2 text-[11px]">
            {research.error ? (
              <span className="text-red-400">{research.error}</span>
            ) : (
              <span className="flex items-center gap-2 text-zinc-300">
                {research.running ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3 text-emerald-400" />}
                {research.message}
              </span>
            )}
          </div>
        )}
        {laborError ? (
          <div className="text-xs text-red-400">{laborError}</div>
        ) : !laborScope ? (
          <div className="text-xs text-zinc-500">Loading…</div>
        ) : laborScope.exhaustiveness.federal.basis === 'none'
            && laborScope.exhaustiveness.state.basis === 'none' ? (
          <div className="text-xs text-amber-400">
            Scope registry is empty — run <span className="font-mono">server/scripts/populate_scope_registry.py</span> to populate it.
          </div>
        ) : (
          <>
            {/* Core spine — the 12-key must-have labor checklist */}
            <div className="mb-4">
              <div className="mb-1 flex items-center gap-2 text-[11px] uppercase text-zinc-500">
                Core labor checklist
                <span className={laborScope.core.complete ? 'text-emerald-400' : 'text-amber-400'}>
                  {laborScope.core.present}/{laborScope.core.total} codified
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {laborScope.core.items.map((it) => (
                  <span
                    key={`${it.category}:${it.key}`}
                    className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[11px] ${
                      it.present
                        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                        : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                    }`}
                    title={it.present ? `codified at ${it.level} level` : 'not yet in jurisdiction-data — to fetch'}
                  >
                    {it.present ? <Check className="h-3 w-3" /> : null}
                    {it.key}
                    {it.present && it.level ? <span className="text-emerald-500/70">·{it.level}</span> : null}
                  </span>
                ))}
              </div>
            </div>

            {/* Federal / State / City — codified vs fetch queue, with honest exhaustiveness */}
            <div className="grid gap-3 md:grid-cols-3">
              {LEVEL_LABELS.map(([lvl, label]) => {
                const data = laborScope.registry.levels[lvl]
                const ex = laborScope.exhaustiveness[lvl]
                // State/city need a state; federal is state-independent.
                if (lvl !== 'federal' && !laborScope.coordinate.state) {
                  return (
                    <div key={lvl} className="rounded border border-dashed border-zinc-800 bg-zinc-950/40 p-3">
                      <div className="mb-1.5 text-xs font-medium text-zinc-400">{label}</div>
                      <div className="text-[11px] text-zinc-600">Set a state above to see {label.toLowerCase()} labor scope.</div>
                    </div>
                  )
                }
                const badge =
                  ex.basis === 'enumerated'
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                    : ex.basis === 'curated'
                      ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
                      : 'border-zinc-700 bg-zinc-800/50 text-zinc-500'
                const badgeText =
                  ex.basis === 'enumerated' ? 'exhaustive (eCFR-enumerated)'
                    : ex.basis === 'curated' ? 'curated core — not exhaustive'
                      : 'no indexes ingested'
                return (
                  <div key={lvl} className="rounded border border-zinc-800 bg-zinc-950/40 p-3">
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-xs font-medium text-zinc-200">{label}</span>
                      <span className={`rounded border px-1.5 py-0.5 text-[10px] ${badge}`} title={ex.note}>
                        {badgeText}
                      </span>
                    </div>
                    {/* WHY this is (or isn't) the exhaustive list */}
                    {ex.note && (
                      <div className="mb-2 text-[11px] leading-snug text-zinc-500">{ex.note}</div>
                    )}
                    {ex.enumeration && ex.enumeration.enumerated > 0 && (
                      <div className="mb-2 text-[11px] text-zinc-400">
                        {ex.enumeration.enumerated} sections enumerated across {ex.enumeration.indexes} authority {ex.enumeration.indexes === 1 ? 'index' : 'indexes'} ·{' '}
                        <span className="text-emerald-400/90">{ex.enumeration.classified} classified</span>
                        {ex.enumeration.unclassified > 0 && (
                          <>
                            {' · '}
                            <span className="text-amber-400/90">{ex.enumeration.unclassified} still to classify</span>
                          </>
                        )}
                      </div>
                    )}
                    {ex.indexes.length > 0 && (
                      <ul className="mb-2 space-y-1">
                        {ex.indexes.map((ix) => (
                          <li key={ix.slug} className="text-[11px] leading-snug">
                            <div className="text-zinc-300">{ix.name || ix.slug}</div>
                            <div className="text-[10px] text-zinc-500">
                              <span className={ix.source_type === 'ecfr' ? 'text-emerald-400/80' : 'text-zinc-400'}>
                                {ix.source_type === 'ecfr'
                                  ? 'eCFR-enumerated (full part, official structure API)'
                                  : 'curated from statute'}
                              </span>
                              {' · '}{ix.item_count} sections
                              {ix.unclassified_count > 0 && (
                                <span className="text-amber-500/80"> · {ix.unclassified_count} unclassified</span>
                              )}
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                    <div className="flex gap-3 text-[11px]">
                      <span className="text-emerald-400">{data.counts.codified} codified</span>
                      <span className="text-amber-400">{data.counts.uncodified} to fetch</span>
                      {data.counts.provisional > 0 && (
                        <span className="text-zinc-500">{data.counts.provisional} awaiting confirm</span>
                      )}
                    </div>
                    {data.codified.length > 0 && (
                      <details className="mt-2">
                        <summary className="cursor-pointer text-[10px] uppercase text-zinc-500">
                          Codified ({data.codified.length})
                        </summary>
                        <ul className="mt-1 space-y-1.5">
                          {data.codified.map((it) => {
                            const r = it.requirement
                            const when = r?.codified_at ?? r?.last_verified_at
                            return (
                              <li key={it.citation} className="text-[11px] text-zinc-400">
                                <div>
                                  <span className="font-mono text-emerald-300/80">{it.citation}</span>
                                  {r?.title ? ` — ${r.title}` : it.regulation_key ? ` — ${it.regulation_key}` : ''}
                                </div>
                                {r?.current_value && (
                                  <div className="text-emerald-200/70">{r.current_value}</div>
                                )}
                                <div className="flex flex-wrap gap-x-2 text-[10px] text-zinc-500">
                                  {r?.source_url ? (
                                    <a href={r.source_url} target="_blank" rel="noreferrer"
                                       className="text-cyan-400/70 hover:underline">
                                      {r.source_name || 'source'}
                                    </a>
                                  ) : r?.source_name ? <span>{r.source_name}</span> : null}
                                  {r?.jurisdiction_name && <span>{r.jurisdiction_name}</span>}
                                  {when && (
                                    <span>{r?.codified_at ? 'codified' : 'verified'} {when.slice(0, 10)}</span>
                                  )}
                                </div>
                              </li>
                            )
                          })}
                        </ul>
                      </details>
                    )}
                    {data.uncodified.length > 0 && (
                      <div className="mt-2">
                        <div className="text-[10px] uppercase text-zinc-500">Fetch queue</div>
                        <ul className="mt-1 space-y-0.5">
                          {data.uncodified.slice(0, 10).map((it) => (
                            <li key={it.citation} className="text-[11px] text-amber-300/80">
                              <span className="font-mono">{it.citation}</span>
                              {it.heading ? <span className="text-zinc-500"> — {it.heading}</span> : ''}
                            </li>
                          ))}
                          {data.uncodified.length > 10 && (
                            <li className="text-[10px] text-zinc-600">+{data.uncodified.length - 10} more</li>
                          )}
                        </ul>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {(laborScope.registry.skipped.category_specific > 0 || laborScope.registry.skipped.conditional > 0) && (
              <div className="mt-2 text-[11px] text-zinc-500">
                {laborScope.registry.skipped.category_specific} category-gated + {laborScope.registry.skipped.conditional} conditional items excluded (generic-employer view)
              </div>
            )}
          </>
        )}
      </div>

      {proposal && (
        <SpecialtyReviewModal
          proposal={proposal}
          industry={industry}
          onCancel={() => setProposal(null)}
          onConfirmed={onSpecialtyConfirmed}
        />
      )}
    </div>
  )
}
