import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../../../api/client'
import { postSSE } from '../../../../api/sse'
import { type DiscoverResponse } from '../SpecialtyReviewModal'
import type { VerticalCoverageResponse } from '../types'
import { GROUP_ORDER, HEADCOUNT_MIDPOINT } from './constants'
import type {
  CategoryEntry,
  GeneralCoverage,
  ItemBody,
  LaborScopeLevel,
  LaborScopeResponse,
  MatrixResponse,
  ResearchState,
  ResolveResult,
  Specialty,
} from './types'

export type UseCoverageParams = {
  initialIndustry?: string | null
  initialState?: string | null
  initialCity?: string | null
  initialHeadcount?: string | null
  onMutate?: () => void
}

export function useCoverage({
  initialIndustry, initialState, initialCity, initialHeadcount, onMutate,
}: UseCoverageParams) {
  const [industry, setIndustry] = useState(initialIndustry || 'healthcare')
  const [state, setState] = useState((initialState || '').toUpperCase())
  const [city, setCity] = useState(initialCity || '')
  const [headcount, setHeadcount] = useState(initialHeadcount || '')
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

  const bumpNonce = useCallback(() => {
    setMatrixNonce((n) => n + 1)
    onMutate?.()
  }, [onMutate])

  const [newSpecialty, setNewSpecialty] = useState('')
  const [discovering, setDiscovering] = useState(false)
  const [proposal, setProposal] = useState<DiscoverResponse | null>(null)
  const [specialtyError, setSpecialtyError] = useState<string | null>(null)
  const [researchTarget, setResearchTarget] =
    useState<{ label: string; industry_tag: string; categories: string[] } | null>(null)

  const [research, setResearch] = useState<ResearchState | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const laborRef = useRef<HTMLDivElement>(null)
  const [coverageTab, setCoverageTab] = useState<'matrix' | 'resolve' | 'industry'>('matrix')

  // Cross-jurisdiction industry grid — one industry across every jurisdiction
  // that has a ledger cell. Statuses are PIPELINE state (pending/in_progress/
  // covered/empty/failed), distinct from the registry-resolution numbers above.
  const [grid, setGrid] = useState<VerticalCoverageResponse | null>(null)
  const [gridLoading, setGridLoading] = useState(false)
  const [gridIndustry, setGridIndustry] = useState(initialIndustry || 'healthcare')
  useEffect(() => {
    if (coverageTab !== 'industry') return
    let cancelled = false
    setGridLoading(true)
    ;(async () => {
      try {
        const params = new URLSearchParams()
        if (gridIndustry.trim()) params.set('industry_tag', gridIndustry.trim())
        const res = await api.get<VerticalCoverageResponse>(`/admin/vertical-coverage?${params.toString()}`)
        if (!cancelled) setGrid(res)
      } catch { if (!cancelled) setGrid(null) }
      finally { if (!cancelled) setGridLoading(false) }
    })()
    return () => { cancelled = true }
  }, [coverageTab, gridIndustry, matrixNonce])

  // Industry-agnostic (core-labor) coverage STATE for this coordinate —
  // covered / empty (researched-nothing) / unchecked (never researched). The
  // point is to stop rendering never-checked categories as a silent green.
  const [generalCov, setGeneralCov] = useState<GeneralCoverage | null>(null)
  useEffect(() => {
    if (!state.trim()) { setGeneralCov(null); return }
    let cancelled = false
    ;(async () => {
      try {
        const params = new URLSearchParams({ state: state.trim().toUpperCase() })
        if (city.trim()) params.set('city', city.trim())
        const res = await api.get<GeneralCoverage>(`/admin/jurisdictions/general-coverage?${params.toString()}`)
        if (!cancelled) setGeneralCov(res)
      } catch { if (!cancelled) setGeneralCov(null) }
    })()
    return () => { cancelled = true }
  }, [state, city, matrixNonce])

  // Statute reader — full regulation text in a right drawer.
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

  const [modelMode, setModelMode] = useState<string>('light')
  useEffect(() => {
    api.get<{ jurisdiction_research_model_mode?: string }>('/admin/platform-settings')
      .then((d) => setModelMode(d.jurisdiction_research_model_mode || 'light'))
      .catch(() => {})
  }, [])

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

  // Labor scope is jurisdiction-only; federal always resolves even with no state.
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
    bumpNonce()
  }

  const streamResearch = async (source: 'gap' | 'queue', path: string, body: unknown) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setResearch({ source, running: true, message: 'Starting research…', completed: 0, total: 0, error: null })

    try {
      await postSSE(
        path,
        body,
        (data) => {
          const event = data as {
            type: string; message?: string; jurisdiction?: string
            progress?: number; total?: number; summary?: { total_requirements?: number }
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
            bumpNonce()
          } else if (event.type === 'error') {
            setResearch((r) => (r ? { ...r, running: false, error: event.message ?? 'Research failed' } : r))
          }
        },
        { signal: ctrl.signal },
      )
    } catch (e) {
      if (ctrl.signal.aborted) return
      setResearch({
        source, running: false, message: '', completed: 0, total: 0,
        error: e instanceof Error ? e.message : 'Research failed',
      })
    }
  }

  const researchTargetGap = () => {
    if (!researchTarget || researchTarget.categories.length === 0) return
    if (!state.trim()) {
      setResearch({ source: 'gap', running: false, message: '', completed: 0, total: 0, error: 'Set a state first.' })
      return
    }
    const cities = city.trim() ? [{ city: city.trim(), state: state.trim().toUpperCase() }] : []
    streamResearch('gap', '/admin/specialization-research/run', {
      specialization: researchTarget.label,
      parent_industry: industry,
      industry_tag: researchTarget.industry_tag,
      categories: researchTarget.categories,
      states: [state.trim().toUpperCase()],
      cities,
      industry_context: '',
    })
  }

  const researchFetchQueue = () => {
    streamResearch('queue', '/admin/scope-registry/fetch-queue/research', {
      state: state.trim() ? state.trim().toUpperCase() : null,
      city: city.trim() || null,
    })
  }

  useEffect(() => () => abortRef.current?.abort(), [])

  return {
    industry, setIndustry, state, setState, city, setCity, headcount, setHeadcount,
    specialties, available,
    matrix, matrixLoading, onlyGaps, setOnlyGaps,
    resolveResult, resolveError,
    laborScope, laborError,
    newSpecialty, setNewSpecialty, discovering, proposal, setProposal,
    specialtyError, researchTarget,
    research,
    laborRef, coverageTab, setCoverageTab,
    grid, gridLoading, gridIndustry, setGridIndustry,
    generalCov,
    reader, setReader, openReader,
    modelMode,
    grouped, kpis,
    toggleSpecialty, discoverSpecialty, onSpecialtyConfirmed,
    researchTargetGap, researchFetchQueue,
  }
}
