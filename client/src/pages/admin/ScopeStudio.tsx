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
import { Microscope, Loader2, Check, BookOpen, Telescope } from 'lucide-react'
import { api, ensureFreshToken } from '../../api/client'
import { Button, Input, LABEL, Select } from '../../components/ui'
import { Drawer } from '../../components/ui/Drawer'
import { HelpHint } from '../../components/ui/HelpHint'
import AuthorityCockpit from '../../components/admin/scope/AuthorityCockpit'

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

// Authority drift (re-ingest diff) change types — the "a law changed" queue.
const DRIFT_BADGE: Record<string, string> = {
  new: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  amended: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  removed: 'bg-red-500/15 text-red-300 border-red-500/30',
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
  // Engine augmentation (present only with a location + a definitively-classified
  // coordinate). 'engine' = the registry grounds this cell's codified/to-codify.
  registry_source?: 'engine' | 'bank'
  engine_codified?: number | null
  engine_to_codify?: number | null
  engine_expected?: number | null
}

type MatrixResponse = {
  summary: {
    total: number; with_data: number; missing_data: number
    engine_cells?: number; engine_to_codify?: number
  }
  scoped_to: { state: string; city: string | null; city_found: boolean | null } | null
  registry_definitive?: boolean
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
  item_id?: string | null
  has_body?: boolean
  source_url?: string | null
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

type RequirementPenalties = {
  enforcing_agency?: string | null
  civil_penalty_min?: number | string | null
  civil_penalty_max?: number | string | null
  per_violation?: boolean | string | null
  annual_cap?: number | string | null
  criminal?: string | null
  summary?: string | null
  grounding?: string | null
}

type LaborScopeRequirement = {
  title?: string | null
  key_definition_id?: string | null
  current_value?: string | null
  source_url?: string | null
  source_name?: string | null
  jurisdiction_name?: string | null
  jurisdiction_level?: string | null
  last_verified_at?: string | null
  codified_at?: string | null
  codify_source?: string | null
  effective_date?: string | null
  expiration_date?: string | null
  penalties?: RequirementPenalties | null
}

type JurisdictionScope = { level: string; names: string[] }

type CodifiedEntry = {
  citation: string; heading: string | null; regulation_key: string | null
  source_url?: string | null; item_id?: string | null; has_body?: boolean
  severity?: string | null; jurisdiction_scope?: JurisdictionScope | null
  requirement?: LaborScopeRequirement | null
}
type UncodifiedEntry = {
  citation: string; heading: string | null; regulation_key: string | null
  source_url?: string | null; item_id?: string | null; has_body?: boolean
  severity?: string | null; jurisdiction_scope?: JurisdictionScope | null
}

type LaborScopeLevel = {
  codified: CodifiedEntry[]
  uncodified: UncodifiedEntry[]
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

// Compact penalty chip text: "≤ $10,000" from civil_penalty_max, else the
// summary truncated. Null when the block has nothing displayable.
function penaltyChipText(p: RequirementPenalties | null | undefined): string | null {
  if (!p) return null
  const max = p.civil_penalty_max
  if (max !== null && max !== undefined && max !== '') {
    const n = typeof max === 'number' ? max : Number(max)
    return Number.isFinite(n) ? `≤ $${n.toLocaleString()}` : `≤ ${max}`
  }
  if (p.summary) return p.summary.length > 40 ? `${p.summary.slice(0, 40)}…` : p.summary
  return null
}

// Obligation severity (RKD) — 'critical' | 'high' | 'moderate' | 'low'. Only the
// two urgent bands render a badge; moderate/low stay quiet to avoid noise.
const SEVERITY_BADGE: Record<string, string> = {
  critical: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  high: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
}
function SeverityBadge({ severity }: { severity?: string | null }) {
  const key = (severity || '').toLowerCase()
  const cls = SEVERITY_BADGE[key]
  if (!cls) return null
  return (
    <span className={`ml-1.5 rounded border px-1 text-[9px] uppercase tracking-wide ${cls}`}
          title={`Severity: ${key}`}>
      {key}
    </span>
  )
}

// Sub-index jurisdiction narrowing — this tag reaches only named counties/cities.
function ScopeChip({ scope }: { scope?: JurisdictionScope | null }) {
  if (!scope || !scope.names?.length) return null
  const plural = scope.level === 'city' ? 'cities' : scope.level === 'county' ? 'counties' : `${scope.level}s`
  return (
    <span className="ml-1.5 rounded border border-sky-500/30 bg-sky-500/15 px-1 text-[9px] text-sky-300"
          title={`Applies only to these ${plural}`}>
      {scope.level}: {scope.names.join(', ')}
    </span>
  )
}

// Reader-aware citation: opens the in-app statute drawer when body text exists,
// else links to the source, else plain text. Module-scope so it isn't a new
// component identity every parent render.
function CitationLink({
  it, onOpen,
}: {
  it: { citation: string; item_id?: string | null; has_body?: boolean; source_url?: string | null }
  onOpen: (itemId: string) => void
}) {
  const cls = 'font-mono text-emerald-300/80 hover:text-emerald-200 hover:underline'
  if (it.has_body && it.item_id) {
    return (
      <button onClick={() => onOpen(it.item_id as string)} className={`${cls} inline-flex items-center gap-1`}
              title="Read the full regulation text">
        {it.citation}<BookOpen className="h-3 w-3 opacity-60" />
      </button>
    )
  }
  if (it.source_url) {
    return (
      <a href={it.source_url} target="_blank" rel="noreferrer" className={cls} title="Read the regulation (source)">
        {it.citation}
      </a>
    )
  }
  return <span className="font-mono text-emerald-300/80">{it.citation}</span>
}

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
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-white/[0.08] bg-zinc-900 p-6">
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
              className="flex cursor-pointer gap-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 hover:border-white/20"
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
            className="rounded-lg border border-white/[0.08] px-4 py-2 text-sm text-zinc-300 hover:bg-white/[0.04]"
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

// ── Small presentational helpers ─────────────────────────────────────────────

// Research (SSE) status — shared shape for the specialty-gap and fetch-queue runs.
type ResearchState = {
  source: 'gap' | 'queue'
  running: boolean; message: string; completed: number; total: number; error: string | null
}

// One cell of the KPI stat strip — Legal Pilot's SystemsStrip idiom (divide-x
// strip, mono tabular numbers, emerald live-accent, staggered fade-in).
function Stat({
  label, value, tone = 'text-zinc-100', hint, onClick, delay = 0,
}: {
  label: string; value: string; tone?: string; hint?: string; onClick?: () => void; delay?: number
}) {
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(id)
  }, [])
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      title={hint}
      style={{ transitionDelay: `${delay}ms` }}
      className={`flex min-w-0 flex-1 flex-col items-start gap-1 px-4 py-3 text-left transition-opacity duration-300 motion-reduce:transition-none ${
        shown ? 'opacity-100' : 'opacity-0'
      } ${onClick ? 'cursor-pointer hover:bg-white/[0.02]' : 'cursor-default'}`}
    >
      <span className={LABEL}>{label}</span>
      <span className={`font-mono text-2xl font-semibold tabular-nums tracking-tight ${tone}`}>{value}</span>
    </button>
  )
}

// Research progress — pulse-dot live header + a real fill bar (completed/total).
function ResearchProgress({ r }: { r: ResearchState }) {
  const pct = r.total > 0 ? Math.min(100, Math.round((r.completed / r.total) * 100)) : r.running ? 0 : 100
  return (
    <div className="mt-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
      {r.error ? (
        <div className="font-mono text-[11px] text-red-400">{r.error}</div>
      ) : (
        <>
          <div className="flex items-center gap-2">
            {r.running
              ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
              : <Check className="h-3.5 w-3.5 text-emerald-400" />}
            <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-emerald-300/90">{r.message}</span>
            {r.total > 0 && <span className="ml-auto font-mono text-[10px] tabular-nums text-zinc-500">{r.completed}/{r.total}</span>}
          </div>
          {(r.running || r.total > 0) && (
            <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-white/[0.06]">
              <div className="h-full rounded-full bg-emerald-400 transition-all duration-500" style={{ width: `${pct}%` }} />
            </div>
          )}
        </>
      )}
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

  // Authority drift review queue — registry-global (not coordinate-driven).
  type DriftRow = {
    id: string
    index_slug: string
    index_name: string
    change_type: 'new' | 'amended' | 'removed'
    citation: string
    heading: string | null
    old_amendment_date: string | null
    new_amendment_date: string | null
    detected_at: string
    status: 'open' | 'acknowledged'
    affected_requirements: number
  }
  const [drift, setDrift] = useState<{ drift: DriftRow[]; open_count: number } | null>(null)
  const [driftError, setDriftError] = useState<string | null>(null)
  const [driftShowAll, setDriftShowAll] = useState(false)
  const [driftNonce, setDriftNonce] = useState(0)
  const [ackBusy, setAckBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const qs = driftShowAll ? '' : '?status=open'
        const res = await api.get<{ drift: DriftRow[]; open_count: number }>(
          `/admin/scope-registry/drift${qs}`,
        )
        if (!cancelled) { setDrift(res); setDriftError(null) }
      } catch (e) {
        if (!cancelled) setDriftError(e instanceof Error ? e.message : 'Failed to load drift')
      }
    })()
    return () => { cancelled = true }
    // matrixNonce: re-sweep after ingest/research mutations elsewhere on the page.
  }, [driftShowAll, driftNonce, matrixNonce])

  const acknowledgeDrift = useCallback(async (ids: string[]) => {
    if (!ids.length) return
    setAckBusy(true)
    try {
      await api.post('/admin/scope-registry/drift/acknowledge', { ids })
      setDriftNonce((n) => n + 1)
    } catch (e) {
      setDriftError(e instanceof Error ? e.message : 'Failed to acknowledge')
    } finally {
      setAckBusy(false)
    }
  }, [])

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
  const [research, setResearch] = useState<ResearchState | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Labor scope is the primary answer; the "To fetch" KPI scrolls here.
  const laborRef = useRef<HTMLDivElement>(null)
  // The secondary industry/specialty section tabs between the two views that
  // used to be a matrix + a permanently-half-empty right rail.
  const [coverageTab, setCoverageTab] = useState<'matrix' | 'resolve'>('matrix')

  // Statute reader — full regulation text in a right drawer.
  type ItemBody = {
    citation: string; heading: string | null; source_url: string | null
    body_text: string | null; body_source_url: string | null
    body_fetched_at: string | null; index_name: string | null
  }
  const [reader, setReader] = useState<{ open: boolean; loading: boolean; body: ItemBody | null }>(
    { open: false, loading: false, body: null },
  )
  const openReader = useCallback(async (itemId: string) => {
    setReader({ open: true, loading: true, body: null })
    try {
      const body = await api.get<ItemBody>(`/admin/scope-registry/items/${itemId}/body`)
      setReader({ open: true, loading: false, body })
    } catch {
      setReader({ open: true, loading: false, body: null })
    }
  }, [])

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

  // KPI headline numbers — driven by Labor scope (the jurisdiction-first engine
  // that always resolves, incl. federal-only). The honest "what must we fetch"
  // counts, summed across federal + state + city.
  const kpis = useMemo(() => {
    if (!laborScope) return null
    const lv = laborScope.registry.levels
    const sum = (pick: (l: LaborScopeLevel) => number) =>
      pick(lv.federal) + pick(lv.state) + pick(lv.city)
    const toClassify = (['federal', 'state', 'city'] as const).reduce(
      (n, l) => n + (laborScope.exhaustiveness[l].enumeration?.unclassified ?? 0), 0,
    )
    return {
      core: `${laborScope.core.present}/${laborScope.core.total}`,
      coreComplete: laborScope.core.complete,
      codified: sum((l) => l.counts.codified),
      toFetch: sum((l) => l.counts.uncodified),
      toClassify,
    }
  }, [laborScope])

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
      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className={LABEL}>Compliance scope registry</div>
          <h1 className="mt-0.5 flex items-center gap-2 text-lg font-semibold tracking-tight text-zinc-100">
            <Telescope className="h-4 w-4 text-emerald-400" /> Scope Studio
          </h1>
          <p className="mt-1 max-w-[70ch] text-sm leading-relaxed text-zinc-500">
            One coordinate → the labor scope you must fetch, its grounded registry resolution, and
            derive → confirm → research the gap.
          </p>
        </div>
        {(() => {
          const info = MODEL_LABELS[modelMode] || MODEL_LABELS.light
          const dot = modelMode === 'heavy' ? 'bg-purple-400' : 'bg-blue-400'
          return (
            <div className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5"
                 title={`Research model: ${info.model}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
              <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-300">{info.label}</span>
              <span className="hidden font-mono text-[10px] tracking-wide text-zinc-600 sm:inline">{info.model}</span>
            </div>
          )
        })()}
      </div>

      {/* Coordinate bar */}
      <div className="mb-4 grid grid-cols-2 gap-4 rounded-xl border border-white/[0.06] bg-zinc-950 p-4 sm:grid-cols-4">
        <div>
          <label className="mb-1.5 block text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-500">Industry</label>
          <Select options={INDUSTRIES} value={industry} onChange={(e) => setIndustry(e.target.value)} />
        </div>
        <div>
          <label className="mb-1.5 block text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-500">State</label>
          <Input value={state} onChange={(e) => setState(e.target.value)} placeholder="CA" maxLength={2} className="uppercase" />
        </div>
        <div>
          <label className="mb-1.5 block text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-500">City (optional)</label>
          <Input value={city} onChange={(e) => setCity(e.target.value)} placeholder="Los Angeles" />
        </div>
        <div>
          <label className="mb-1.5 block text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-500">Headcount</label>
          <Select options={HEADCOUNTS.map((h) => ({ value: h, label: h || 'Any' }))} value={headcount}
                  onChange={(e) => setHeadcount(e.target.value)} />
        </div>
      </div>

      {/* KPI headline strip — the honest "what must we fetch" numbers (jurisdiction axis, from Labor scope) */}
      <div className="mb-5 flex items-stretch divide-x divide-white/[0.06] overflow-x-auto rounded-xl border border-white/[0.06] bg-zinc-950">
        <Stat label="Core labor" value={kpis ? kpis.core : '—'} delay={0}
              tone={kpis ? (kpis.coreComplete ? 'text-emerald-400' : 'text-amber-400') : 'text-zinc-600'} />
        <Stat label="Codified" value={kpis ? String(kpis.codified) : '—'} delay={40}
              tone={kpis ? 'text-emerald-400' : 'text-zinc-600'} />
        <Stat label="To fetch" value={kpis ? String(kpis.toFetch) : '—'} delay={80}
              tone={kpis ? (kpis.toFetch > 0 ? 'text-amber-400' : 'text-emerald-400') : 'text-zinc-600'}
              hint={kpis && kpis.toFetch > 0 ? 'Jump to the labor worklist' : undefined}
              onClick={kpis && kpis.toFetch > 0
                ? () => laborRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                : undefined} />
        <Stat label="To classify" value={kpis ? String(kpis.toClassify) : '—'} delay={120}
              tone={kpis && kpis.toClassify > 0 ? 'text-amber-400' : kpis ? 'text-zinc-300' : 'text-zinc-600'} />
      </div>

      {/* Labor scope — PRIMARY: the authoritative "what must we fetch" view (jurisdiction-first) */}
      <div ref={laborRef} className="rounded-xl border border-white/[0.06] bg-zinc-950 p-4">
        <div className="mb-2 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className={LABEL}>Labor scope — what we must fetch</div>
            <h2 className="mt-0.5 text-base font-semibold tracking-tight text-zinc-100">
              {laborScope?.coordinate.state
                ? `${laborScope.coordinate.state}${laborScope.coordinate.city ? `, ${laborScope.coordinate.city}` : ''}`
                : 'Federal'}
              <span className="ml-2 font-mono text-[10px] font-normal uppercase tracking-[0.15em] text-zinc-600">
                generic employer · federal + state + city
              </span>
            </h2>
          </div>
          {laborScope
            && (['federal', 'state', 'city'] as const).some((l) => laborScope.registry.levels[l].counts.uncodified > 0) && (
            <Button variant="secondary" size="sm" onClick={researchFetchQueue} disabled={research?.running}>
              <Microscope className="h-3.5 w-3.5" />
              Research these · codify
            </Button>
          )}
        </div>
        {research && research.source === 'queue' && <ResearchProgress r={research} />}
        {laborError ? (
          <div className="text-xs text-red-400">{laborError}</div>
        ) : !laborScope ? (
          <div className="text-xs text-zinc-500">Loading…</div>
        ) : laborScope.exhaustiveness.federal.basis === 'none'
            && laborScope.exhaustiveness.state.basis === 'none' ? (
          <div className="text-xs text-amber-400">
            Scope registry is empty — use the <span className="text-zinc-300">Codification cockpit</span> below
            to ingest an authority index, classify it, and confirm the classifications. Until then every
            surface here falls back to the compliance catalog.
          </div>
        ) : (
          <>
            {/* Core spine — the 12-key must-have labor checklist */}
            <div className="mb-4">
              <div className="mb-1.5 flex items-center gap-2">
                <span className={LABEL}>Core labor checklist</span>
                <span className={`font-mono text-[10px] tabular-nums ${laborScope.core.complete ? 'text-emerald-400' : 'text-amber-400'}`}>
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
                    <div key={lvl} className="rounded-lg border border-dashed border-white/[0.08] bg-white/[0.02] p-3">
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
                  <div key={lvl} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-xs font-medium text-zinc-200">{label}</span>
                      <span className="inline-flex items-center gap-1">
                        <span className={`rounded border px-1.5 py-0.5 text-[10px] ${badge}`}>
                          {badgeText}
                        </span>
                        {/* WHY this is (or isn't) the exhaustive list — on demand */}
                        {ex.note && <HelpHint text={ex.note} align="right" />}
                      </span>
                    </div>
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
                            const penaltyChip = penaltyChipText(r?.penalties)
                            const policyHref = r?.key_definition_id
                              ? `/admin/jurisdiction-data/policy/${r.key_definition_id}`
                              : null
                            return (
                              <li key={it.citation} className="text-[11px] text-zinc-400">
                                <div>
                                  {/* Citation → in-app statute reader (or source) */}
                                  <CitationLink it={it} onOpen={openReader} />
                                  {r?.title ? ` — ${r.title}` : it.regulation_key ? ` — ${it.regulation_key}` : ''}
                                  <SeverityBadge severity={it.severity} />
                                  <ScopeChip scope={it.jurisdiction_scope} />
                                  {policyHref && (
                                    <a href={policyHref}
                                       className="ml-1.5 text-[10px] text-cyan-400/70 hover:underline"
                                       title="Open the codified value in the Compliance Library">
                                      library ↗
                                    </a>
                                  )}
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
                                  {r?.effective_date && (
                                    <span>effective {r.effective_date.slice(0, 10)}</span>
                                  )}
                                  {penaltyChip && (
                                    <span className="text-amber-400/80"
                                          title={r?.penalties?.summary || undefined}>
                                      penalty {penaltyChip}
                                    </span>
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
                              {it.has_body && it.item_id ? (
                                <button onClick={() => openReader(it.item_id as string)}
                                        className="inline-flex items-center gap-1 font-mono hover:underline"
                                        title="Read the full regulation text">
                                  {it.citation}<BookOpen className="h-3 w-3 opacity-60" />
                                </button>
                              ) : (
                                <span className="font-mono">{it.citation}</span>
                              )}
                              {it.heading ? <span className="text-zinc-500"> — {it.heading}</span> : ''}
                              <SeverityBadge severity={it.severity} />
                              <ScopeChip scope={it.jurisdiction_scope} />
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

      {/* Industry & specialty coverage — SECONDARY: the specialization layer on top of core labor */}
      <div className="mt-5 rounded-xl border border-white/[0.06] bg-zinc-950 p-4">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className={LABEL}>Industry &amp; specialty coverage</div>
            <div className="mt-0.5 text-[11px] text-zinc-500">The specialization layer that rides on top of the core labor scope above.</div>
          </div>
          <div className="flex items-center gap-1 rounded-lg border border-white/[0.06] bg-white/[0.02] p-0.5">
            {(['matrix', 'resolve'] as const).map((t) => (
              <button key={t} onClick={() => setCoverageTab(t)}
                className={`rounded px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.15em] transition-colors ${
                  coverageTab === t ? 'bg-white/[0.06] text-zinc-200' : 'text-zinc-500 hover:text-zinc-300'
                }`}>
                {t === 'matrix' ? 'Coverage matrix' : 'Registry resolution'}
              </button>
            ))}
          </div>
        </div>

        {/* Specialties + research the gap */}
        <div className="mb-4 rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
          <div className={`mb-2 ${LABEL}`}>Specialties</div>
          <div className="flex flex-wrap gap-2">
            {available.map((s) => (
              <button
                key={s.slug}
                onClick={() => toggleSpecialty(s.slug)}
                className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                  specialties.includes(s.slug)
                    ? 'border-purple-500/50 bg-purple-500/15 text-purple-200'
                    : 'border-white/[0.08] text-zinc-400 hover:border-white/20'
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
              className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.02] px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-white/20"
            />
            <Button variant="secondary" size="sm" onClick={discoverSpecialty} disabled={discovering || !newSpecialty.trim()}>
              {discovering ? '…' : 'Derive ↵'}
            </Button>
          </div>
          {specialtyError && <div className="mt-2 text-xs text-red-400">{specialtyError}</div>}
          {researchTarget && researchTarget.categories.length > 0 && (
            <div className="mt-3">
              <Button variant="primary" size="sm" onClick={researchTargetGap} disabled={research?.running || !state.trim()}>
                <Microscope className="h-3.5 w-3.5" />
                Research {researchTarget.label} — {researchTarget.categories.length} categories
                {!state.trim() && <span className="text-amber-300"> · set a state</span>}
              </Button>
            </div>
          )}
          {research && research.source === 'gap' && <ResearchProgress r={research} />}
        </div>

        {coverageTab === 'matrix' ? (
          <>
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
                  {matrix.summary.missing_data} to fetch
                </button>
                {matrix.scoped_to?.city && matrix.scoped_to.city_found === false && (
                  <span className="text-xs text-amber-400">city not found — state ∪ federal</span>
                )}
                {(matrix.summary.engine_cells ?? 0) > 0 && (
                  <span className={`rounded border px-2 py-0.5 text-xs ${SOURCE_BADGE.base}`}>
                    {matrix.summary.engine_cells} engine-grounded · {matrix.summary.engine_to_codify ?? 0} to codify
                  </span>
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
                              {c.registry_source === 'engine' && (
                                <span className="ml-2 inline-flex items-center gap-1">
                                  <span className={`rounded border px-1.5 py-0.5 text-[10px] ${SOURCE_BADGE.base}`}>
                                    engine
                                  </span>
                                  <span className="text-zinc-400">
                                    {c.engine_codified ?? 0} codified · {c.engine_to_codify ?? 0} to codify
                                  </span>
                                </span>
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
          </>
        ) : (
          <>
            {!state.trim() ? (
              <div className="py-6 text-center text-xs text-zinc-500">Set a state to resolve the grounded registry scope.</div>
            ) : resolveError ? (
              <div className="text-xs text-red-400">{resolveError}</div>
            ) : !resolveResult ? (
              <div className="py-6 text-center text-xs text-zinc-500">Resolving…</div>
            ) : (
              <>
                <div className="flex flex-wrap gap-3 text-xs">
                  <span className="text-zinc-300">{resolveResult.counts.applicable} applicable</span>
                  <span className="text-emerald-400">{resolveResult.counts.codified} codified</span>
                  <span className="text-amber-400">{resolveResult.counts.uncodified} to fetch</span>
                  {resolveResult.counts.provisional > 0 && (
                    <span className="text-zinc-500">{resolveResult.counts.provisional} provisional (excluded)</span>
                  )}
                </div>
                {resolveResult.uncodified.length > 0 && (
                  <div className="mt-3">
                    <div className="text-[11px] uppercase text-zinc-500">To fetch</div>
                    <ul className="mt-1 grid gap-1 sm:grid-cols-2">
                      {resolveResult.uncodified.slice(0, 20).map((it) => (
                        <li key={it.citation} className="text-xs text-zinc-400">
                          <CitationLink it={it} onOpen={openReader} />
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
          </>
        )}
      </div>

      {/* Authority drift — new/amended/removed citations detected on re-ingest */}
      <div className="mt-5 rounded-xl border border-white/[0.06] bg-zinc-950 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className={LABEL}>Authority drift</div>
            <HelpHint text="What changed at the source since the last ingest of each authority index — a new section appeared, a heading was amended, or a citation vanished upstream. Review each row, act on it (research / reclassify), then acknowledge it to clear the queue." />
            {drift && drift.open_count > 0 && (
              <span className={`rounded border px-1.5 py-0.5 text-[10px] ${DRIFT_BADGE.amended}`}>
                {drift.open_count} open
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setDriftShowAll((v) => !v)}
              className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-zinc-400 hover:border-white/20">
              {driftShowAll ? 'Show open only' : 'Show all (incl. acknowledged)'}
            </button>
            {drift && drift.drift.some((d) => d.status === 'open') && (
              <button
                disabled={ackBusy}
                onClick={() => acknowledgeDrift(drift.drift.filter((d) => d.status === 'open').map((d) => d.id))}
                className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-emerald-300 hover:border-white/20 disabled:opacity-50">
                {ackBusy ? 'Acknowledging…' : 'Acknowledge all shown'}
              </button>
            )}
          </div>
        </div>

        {driftError ? (
          <div className="text-xs text-red-400">{driftError}</div>
        ) : !drift ? (
          <div className="text-xs text-zinc-500">Loading…</div>
        ) : drift.drift.length === 0 ? (
          <div className="text-xs text-zinc-500">
            {driftShowAll
              ? 'No drift recorded yet — run an ingest twice to establish a baseline and diff against it.'
              : 'No open drift. The authority indexes match their last-reviewed state.'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-zinc-500">
                <tr>
                  <th className="py-2">Change</th>
                  <th className="py-2">Citation</th>
                  <th className="py-2">Index</th>
                  <th className="py-2">Affected</th>
                  <th className="py-2">Detected</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {drift.drift.map((d) => (
                  <tr key={d.id} className={d.status === 'acknowledged' ? 'opacity-50' : ''}>
                    <td className="py-1.5">
                      <span className={`rounded border px-1.5 py-0.5 text-[10px] ${DRIFT_BADGE[d.change_type]}`}>
                        {d.change_type}
                      </span>
                    </td>
                    <td className="py-1.5 text-zinc-200">
                      <span className="font-mono">{d.citation}</span>
                      {d.heading && <span className="text-zinc-500"> — {d.heading}</span>}
                    </td>
                    <td className="py-1.5 text-xs text-zinc-400">{d.index_slug}</td>
                    <td className="py-1.5 text-xs">
                      {d.affected_requirements > 0 ? (
                        <span className="rounded bg-purple-500/15 px-1.5 py-0.5 text-[10px] text-purple-300"
                              title="Codified policy rows flagged needs_review by this change">
                          {d.affected_requirements} {d.affected_requirements === 1 ? 'policy' : 'policies'}
                        </span>
                      ) : (
                        <span className="text-zinc-600">—</span>
                      )}
                    </td>
                    <td className="py-1.5 text-xs text-zinc-500">{d.detected_at.slice(0, 10)}</td>
                    <td className="py-1.5 text-right">
                      {d.status === 'open' ? (
                        <button
                          disabled={ackBusy}
                          onClick={() => acknowledgeDrift([d.id])}
                          className="rounded border border-white/[0.08] px-2 py-0.5 text-[11px] text-zinc-300 hover:border-white/20 disabled:opacity-50"
                          title="Mark reviewed — clears it from the open queue (kept for audit)">
                          <Check className="inline h-3 w-3" /> Ack
                        </button>
                      ) : (
                        <span className="text-[10px] uppercase text-zinc-600">acknowledged</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* The authoring pipeline: ingest → classify → confirm/key → reconcile.
          Every surface above READS the registry; this is the only one that
          fills it. */}
      <AuthorityCockpit onMutate={() => setMatrixNonce((n) => n + 1)} />

      {proposal && (
        <SpecialtyReviewModal
          proposal={proposal}
          industry={industry}
          onCancel={() => setProposal(null)}
          onConfirmed={onSpecialtyConfirmed}
        />
      )}

      {/* Statute reader — the full regulation text, in-app */}
      <Drawer
        open={reader.open}
        onClose={() => setReader({ open: false, loading: false, body: null })}
        width="xl"
        title={reader.body?.citation ?? (reader.loading ? 'Loading…' : 'Statute')}
        subtitle={reader.body ? (
          <span className="flex flex-wrap items-center gap-2">
            {reader.body.heading && <span className="text-zinc-400">{reader.body.heading}</span>}
            {reader.body.index_name && <span>· {reader.body.index_name}</span>}
            {(reader.body.body_source_url || reader.body.source_url) && (
              <a href={reader.body.body_source_url || reader.body.source_url || undefined}
                 target="_blank" rel="noreferrer" className="text-cyan-400/70 hover:underline">source ↗</a>
            )}
            {reader.body.body_fetched_at && <span>· fetched {reader.body.body_fetched_at.slice(0, 10)}</span>}
          </span>
        ) : null}
      >
        {reader.loading ? (
          <div className="flex items-center gap-2 text-sm text-zinc-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading the regulation text…
          </div>
        ) : reader.body?.body_text ? (
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-zinc-300">
            {reader.body.body_text}
          </pre>
        ) : reader.body ? (
          <div className="text-sm text-zinc-500">
            No stored text for this item yet.{' '}
            {(reader.body.source_url) && (
              <a href={reader.body.source_url} target="_blank" rel="noreferrer" className="text-cyan-400/70 hover:underline">
                Read at the source ↗
              </a>
            )}
          </div>
        ) : (
          <div className="text-sm text-red-400">Failed to load.</div>
        )}
      </Drawer>
    </div>
  )
}
