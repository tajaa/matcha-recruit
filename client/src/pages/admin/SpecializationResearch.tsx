import { useState, useRef } from 'react'
import { Microscope, Loader2, Check, ChevronRight, ArrowLeft } from 'lucide-react'

// ── Types ──────────────────────────────────────────────────────────────────────

type DiscoveredCategory = {
  key: string
  label: string
  description: string
  is_existing: boolean
}

type DiscoverResponse = {
  categories: DiscoveredCategory[]
  industry_tag: string
  industry_context: string
}

type JurisdictionProgress = {
  jurisdiction: string
  category: string
  requirements_found: number
  done: boolean
}

type CompletedJurisdiction = {
  jurisdiction: string
  requirement_count: number
}

// ── Constants ──────────────────────────────────────────────────────────────────

const PARENT_INDUSTRIES = [
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'restaurant_hospitality', label: 'Restaurant/Hospitality' },
  { value: 'retail', label: 'Retail' },
  { value: 'tech_professional', label: 'Tech/Professional Services' },
  { value: 'construction_manufacturing', label: 'Construction/Manufacturing' },
]

const BASE = import.meta.env.VITE_API_URL ?? '/api'

// ── Component ──────────────────────────────────────────────────────────────────

export default function SpecializationResearch() {
  const [step, setStep] = useState(1)

  // Step 1 state
  const [specialization, setSpecialization] = useState('')
  const [parentIndustry, setParentIndustry] = useState('healthcare')
  const [discovering, setDiscovering] = useState(false)
  const [discoverError, setDiscoverError] = useState('')

  // Step 2 state
  const [discoveryResult, setDiscoveryResult] = useState<DiscoverResponse | null>(null)
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(new Set())
  const [statesInput, setStatesInput] = useState('')
  const [citiesInput, setCitiesInput] = useState('')

  // Step 3 state
  const [statusMessage, setStatusMessage] = useState('')
  const [jurisdictionProgress, setJurisdictionProgress] = useState<Map<string, JurisdictionProgress>>(new Map())
  const [completedJurisdictions, setCompletedJurisdictions] = useState<CompletedJurisdiction[]>([])
  const [finalSummary, setFinalSummary] = useState<{
    total_requirements: number
    jurisdictions_researched: number
    coverage_pct: number
  } | null>(null)
  const [researchError, setResearchError] = useState('')
  const [researching, setResearching] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  // ── Step 1: Discover ─────────────────────────────────────────────────────────

  async function handleDiscover() {
    if (!specialization.trim()) return
    setDiscovering(true)
    setDiscoverError('')
    const token = localStorage.getItem('matcha_access_token')
    try {
      const res = await fetch(`${BASE}/admin/specialization-research/discover`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ specialization: specialization.trim(), parent_industry: parentIndustry }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.detail ?? `Request failed (${res.status})`)
      }
      const data: DiscoverResponse = await res.json()
      setDiscoveryResult(data)
      setSelectedCategories(new Set(data.categories.map((c) => c.key)))
      setStep(2)
    } catch (err: any) {
      setDiscoverError(err.message || 'Discovery failed')
    } finally {
      setDiscovering(false)
    }
  }

  // ── Step 2 → 3: Start research ──────────────────────────────────────────────

  function parseCities(input: string): { city: string; state: string }[] {
    if (!input.trim()) return []
    return input
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((entry) => {
        const match = entry.match(/^(.+?)\s*\((\w{2})\)$/)
        if (match) return { city: match[1].trim(), state: match[2].toUpperCase() }
        return null
      })
      .filter((c): c is { city: string; state: string } => c !== null)
  }

  function parseStates(input: string): string[] {
    if (!input.trim()) return []
    return input
      .split(',')
      .map((s) => s.trim().toUpperCase())
      .filter((s) => s.length === 2)
  }

  async function handleStartResearch() {
    if (!discoveryResult) return
    const categories = discoveryResult.categories.filter((c) => selectedCategories.has(c.key))
    const states = parseStates(statesInput)
    const cities = parseCities(citiesInput)

    // Reset step 3 state
    setStatusMessage('Starting research...')
    setJurisdictionProgress(new Map())
    setCompletedJurisdictions([])
    setFinalSummary(null)
    setResearchError('')
    setResearching(true)
    setStep(3)

    const token = localStorage.getItem('matcha_access_token')
    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      const res = await fetch(`${BASE}/admin/specialization-research/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          specialization: specialization.trim(),
          parent_industry: parentIndustry,
          industry_tag: discoveryResult.industry_tag,
          categories: categories.map((c) => c.key),
          states,
          cities,
          industry_context: discoveryResult.industry_context,
        }),
        signal: ctrl.signal,
      })

      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.detail ?? `Request failed (${res.status})`)
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
          const event = JSON.parse(line.slice(6))

          if (event.type === 'status') {
            setStatusMessage(event.message)
          } else if (event.type === 'researching') {
            setStatusMessage(`Researching ${event.jurisdiction}... (${event.progress}/${event.total})`)
            setJurisdictionProgress((prev) => {
              const next = new Map(prev)
              next.set(event.jurisdiction, {
                jurisdiction: event.jurisdiction,
                category: '',
                requirements_found: 0,
                done: false,
              })
              return next
            })
          } else if (event.type === 'jurisdiction_complete') {
            setJurisdictionProgress((prev) => {
              const next = new Map(prev)
              next.delete(event.jurisdiction)
              return next
            })
            setCompletedJurisdictions((prev) => [
              ...prev,
              { jurisdiction: event.jurisdiction, requirement_count: event.requirements_found ?? 0 },
            ])
          } else if (event.type === 'completed') {
            const s = event.summary ?? {}
            setFinalSummary({
              total_requirements: s.total_requirements ?? 0,
              jurisdictions_researched: s.jurisdictions_researched ?? 0,
              coverage_pct: 0,
            })
            setStatusMessage(`Found ${s.total_requirements ?? 0} requirements for ${specialization}`)
            setResearching(false)
          } else if (event.type === 'error') {
            setResearchError(event.message ?? 'Research failed')
            setResearching(false)
          }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setResearchError(err.message || 'Research failed')
      }
      setResearching(false)
    }
  }

  // ── Step indicator ───────────────────────────────────────────────────────────

  const steps = ['Discover', 'Configure', 'Research']

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <Microscope className="w-6 h-6 text-emerald-400" />
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">Specialization Research</h1>
          <p className="text-sm text-zinc-500">Discover and research compliance categories for industry specializations</p>
        </div>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-8">
        {steps.map((label, i) => {
          const stepNum = i + 1
          const isActive = step === stepNum
          const isDone = step > stepNum
          return (
            <div key={label} className="flex items-center gap-2">
              {i > 0 && <ChevronRight className="w-4 h-4 text-zinc-600" />}
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${
                isActive
                  ? 'bg-emerald-900/30 text-emerald-400 border border-emerald-800/40'
                  : isDone
                    ? 'bg-zinc-800 text-zinc-300 border border-zinc-700'
                    : 'text-zinc-600'
              }`}>
                {isDone ? <Check className="w-3.5 h-3.5" /> : <span>{stepNum}</span>}
                {label}
              </div>
            </div>
          )
        })}
      </div>

      {/* ── Step 1: Discover ── */}
      {step === 1 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-5">
          <div>
            <label className="block text-[10px] uppercase tracking-wide text-zinc-500 font-medium mb-1.5">
              Specialization Name
            </label>
            <input
              type="text"
              value={specialization}
              onChange={(e) => setSpecialization(e.target.value)}
              placeholder="e.g., Cardiology, Orthopedics, Psychiatry..."
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-200 text-sm px-3 py-2 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-600"
            />
          </div>

          <div>
            <label className="block text-[10px] uppercase tracking-wide text-zinc-500 font-medium mb-1.5">
              Parent Industry
            </label>
            <select
              value={parentIndustry}
              onChange={(e) => setParentIndustry(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-200 text-sm px-3 py-2 focus:outline-none focus:border-emerald-600"
            >
              {PARENT_INDUSTRIES.map((ind) => (
                <option key={ind.value} value={ind.value}>{ind.label}</option>
              ))}
            </select>
          </div>

          {discoverError && (
            <p className="text-sm text-red-400">{discoverError}</p>
          )}

          <button
            onClick={handleDiscover}
            disabled={!specialization.trim() || discovering}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            {discovering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Microscope className="w-4 h-4" />}
            Discover Categories
          </button>
        </div>
      )}

      {/* ── Step 2: Configure ── */}
      {step === 2 && discoveryResult && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 space-y-6">
          {/* Industry tag label */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wide text-zinc-500 font-medium">Industry Tag:</span>
            <span className="inline-block rounded-md px-2 py-0.5 text-xs font-mono bg-zinc-800 text-zinc-300 border border-zinc-700">
              {discoveryResult.industry_tag}
            </span>
          </div>

          {/* Category checklist */}
          <div>
            <label className="block text-[10px] uppercase tracking-wide text-zinc-500 font-medium mb-2">
              Categories ({selectedCategories.size}/{discoveryResult.categories.length} selected)
            </label>
            <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
              {discoveryResult.categories.map((cat) => (
                <label
                  key={cat.key}
                  className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-zinc-800/50 cursor-pointer transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={selectedCategories.has(cat.key)}
                    onChange={() => {
                      setSelectedCategories((prev) => {
                        const next = new Set(prev)
                        if (next.has(cat.key)) next.delete(cat.key)
                        else next.add(cat.key)
                        return next
                      })
                    }}
                    className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500/30 w-4 h-4 mt-0.5"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-zinc-200">{cat.label}</span>
                      {cat.is_existing ? (
                        <span className="inline-block rounded-md px-1.5 py-0.5 text-[10px] font-medium bg-emerald-900/30 text-emerald-400 border border-emerald-800/40">
                          Existing
                        </span>
                      ) : (
                        <span className="inline-block rounded-md px-1.5 py-0.5 text-[10px] font-medium bg-amber-900/30 text-amber-400 border border-amber-800/40">
                          New
                        </span>
                      )}
                    </div>
                    {cat.description && (
                      <p className="text-xs text-zinc-500 mt-0.5">{cat.description}</p>
                    )}
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Jurisdictions */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] uppercase tracking-wide text-zinc-500 font-medium mb-1.5">
                States (comma-separated)
              </label>
              <input
                type="text"
                value={statesInput}
                onChange={(e) => setStatesInput(e.target.value)}
                placeholder="CA, NY, TX"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-200 text-sm px-3 py-2 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-600"
              />
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-wide text-zinc-500 font-medium mb-1.5">
                Cities (comma-separated)
              </label>
              <input
                type="text"
                value={citiesInput}
                onChange={(e) => setCitiesInput(e.target.value)}
                placeholder="Los Angeles (CA), New York (NY)"
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg text-zinc-200 text-sm px-3 py-2 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-600"
              />
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setStep(1)}
              className="flex items-center gap-2 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
            <button
              onClick={handleStartResearch}
              disabled={selectedCategories.size === 0}
              className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              <Microscope className="w-4 h-4" />
              Start Research
            </button>
          </div>
        </div>
      )}

      {/* ── Step 3: Progress + Results ── */}
      {step === 3 && (
        <div className="space-y-4">
          {/* Status */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 flex items-center gap-3">
            {researching ? (
              <Loader2 className="w-5 h-5 text-emerald-400 animate-spin" />
            ) : finalSummary ? (
              <Check className="w-5 h-5 text-emerald-400" />
            ) : (
              <Microscope className="w-5 h-5 text-zinc-500" />
            )}
            <span className="text-sm text-zinc-300">{statusMessage}</span>
          </div>

          {/* Active jurisdiction progress */}
          {jurisdictionProgress.size > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
              <h3 className="text-[10px] uppercase tracking-wide text-zinc-500 font-medium mb-3">In Progress</h3>
              <div className="space-y-2">
                {[...jurisdictionProgress.values()].map((jp) => (
                  <div key={jp.jurisdiction} className="flex items-center gap-3">
                    <Loader2 className="w-3.5 h-3.5 text-emerald-400 animate-spin shrink-0" />
                    <span className="text-sm text-zinc-300 font-medium">{jp.jurisdiction}</span>
                    <span className="text-xs text-zinc-500">{jp.category}</span>
                    {jp.requirements_found > 0 && (
                      <span className="text-xs text-emerald-400 ml-auto">{jp.requirements_found} found</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Completed jurisdictions */}
          {completedJurisdictions.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4">
              <h3 className="text-[10px] uppercase tracking-wide text-zinc-500 font-medium mb-3">
                Completed ({completedJurisdictions.length})
              </h3>
              <div className="space-y-1.5">
                {completedJurisdictions.map((cj) => (
                  <div key={cj.jurisdiction} className="flex items-center gap-3">
                    <Check className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                    <span className="text-sm text-zinc-300">{cj.jurisdiction}</span>
                    <span className="text-xs text-zinc-500 ml-auto">
                      {cj.requirement_count} requirement{cj.requirement_count !== 1 ? 's' : ''}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Final summary */}
          {finalSummary && (
            <div className="bg-emerald-950/30 border border-emerald-800/40 rounded-lg p-6 text-center">
              <p className="text-lg font-semibold text-emerald-300 font-[Space_Grotesk]">
                Found {finalSummary.total_requirements} requirements for {specialization} across{' '}
                {finalSummary.jurisdictions_researched} jurisdictions
              </p>
              <div className="flex items-center justify-center gap-6 mt-4">
                <div>
                  <span className="block text-2xl font-bold font-mono text-zinc-100">
                    {finalSummary.total_requirements}
                  </span>
                  <span className="text-xs text-zinc-500">Requirements</span>
                </div>
                <div className="w-px h-10 bg-zinc-700" />
                <div>
                  <span className="block text-2xl font-bold font-mono text-zinc-100">
                    {finalSummary.jurisdictions_researched}
                  </span>
                  <span className="text-xs text-zinc-500">Jurisdictions</span>
                </div>
                <div className="w-px h-10 bg-zinc-700" />
                <div>
                  <span className="block text-2xl font-bold font-mono text-zinc-100">
                    {finalSummary.coverage_pct}%
                  </span>
                  <span className="text-xs text-zinc-500">Coverage</span>
                </div>
              </div>
              <button
                onClick={() => {
                  setStep(1)
                  setSpecialization('')
                  setDiscoveryResult(null)
                  setSelectedCategories(new Set())
                  setStatesInput('')
                  setCitiesInput('')
                  setStatusMessage('')
                  setJurisdictionProgress(new Map())
                  setCompletedJurisdictions([])
                  setFinalSummary(null)
                }}
                className="mt-4 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 text-sm font-medium px-4 py-2 rounded-lg transition-colors"
              >
                Start New Research
              </button>
            </div>
          )}

          {/* Error */}
          {researchError && (
            <div className="bg-red-950/30 border border-red-800/40 rounded-lg p-4">
              <p className="text-sm text-red-400">{researchError}</p>
              <button
                onClick={() => setStep(2)}
                className="mt-2 flex items-center gap-2 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 text-sm font-medium px-4 py-2 rounded-lg transition-colors"
              >
                <ArrowLeft className="w-4 h-4" />
                Back to Configure
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
