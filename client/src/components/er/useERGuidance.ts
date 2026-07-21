import { useState, useEffect, useRef } from 'react'
import { api } from '../../api/client'
import { postSSE } from '../../api/sse'
import type { SuggestedGuidanceResponse, ERCaseOutcome, OutcomeOption, OutcomeAnalysisResponse, ERDocument } from '../../types/er'


// Document-processing poll cadence. The cap (~45s) bounds the wait for a
// document that never finishes parsing; the server-side sweep marks such rows
// 'failed' within 15 min, so this always gives up well ahead of that.
const DOC_POLL_INTERVAL_MS = 3000
const MAX_DOC_POLL_ATTEMPTS = 15


type UseERGuidanceArgs = {
  caseId: string
  guidance: SuggestedGuidanceResponse | null
  onGuidanceChange: (g: SuggestedGuidanceResponse | null) => void
  onGuidanceGenerated?: (g: SuggestedGuidanceResponse) => void
  hasDescription: boolean
  caseStatus?: string
  onBeginDetermination?: (outcome: ERCaseOutcome, adminNotes: string, outcomeDetail?: OutcomeOption) => Promise<void>
  skipCache?: boolean
  onCacheSkipped?: () => void
}

export function useERGuidance({
  caseId,
  guidance,
  onGuidanceChange,
  onGuidanceGenerated,
  hasDescription,
  caseStatus,
  onBeginDetermination,
  skipCache,
  onCacheSkipped,
}: UseERGuidanceArgs) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [determinationDismissed, setDeterminationDismissed] = useState(false)
  const [showDetermination, setShowDetermination] = useState(false)
  const [outcomeData, setOutcomeData] = useState<OutcomeAnalysisResponse | null>(null)
  const [outcomeLoading, setOutcomeLoading] = useState(false)
  const [outcomePhase, setOutcomePhase] = useState('')
  const [outcomeError, setOutcomeError] = useState('')
  const [applying, setApplying] = useState<string | null>(null)
  const [expandedOutcomes, setExpandedOutcomes] = useState<Set<number>>(new Set())
  const [adminNotes, setAdminNotes] = useState<Record<number, string>>({})
  const abortRef = useRef<AbortController | null>(null)

  const isClosed = caseStatus === 'closed'

  // Document processing state, polled from the server. Guidance must wait for at
  // least one document to finish parsing — otherwise the fallback (which counts
  // only `completed` non-policy docs) nags "upload a complaint" even though one
  // was just uploaded at intake and is still being processed.
  const [docStats, setDocStats] = useState<{ completed: number; processing: number; total: number } | null>(null)
  const completedCount = docStats?.completed ?? 0
  const processingCount = docStats?.processing ?? 0
  const totalDocs = docStats?.total ?? 0
  const isProcessing = processingCount > 0 && completedCount === 0
  const hasReadyContent = completedCount > 0 || hasDescription

  // Tracks whether we've already done the initial cache-fetch on this mount.
  // Distinguishes "first mount with no guidance" (→ try cache first)
  // from "guidance cleared by parent after upload" (→ regenerate directly).
  const hasFetchedCache = useRef(false)

  // Poll document processing status while there's no guidance yet and something
  // is still parsing. Keyed on [caseId, guidance] so a Documents-tab upload
  // (which sets guidance back to null) restarts polling for the new file.
  //
  // The poll is capped: a worker killed mid-parse (OOM) used to leave the row
  // in 'processing' forever, and this loop would spin against it for the life
  // of the tab. The server now releases such rows, but never let the UI depend
  // on that — after the cap we stop and fall through to the empty state, which
  // tells the user processing did not complete. Re-opening the case starts a
  // fresh budget, so a document still parsing is picked back up.
  useEffect(() => {
    if (guidance !== null) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    let attempts = 0
    async function poll() {
      try {
        const docs = await api.get<ERDocument[]>(`/er/cases/${caseId}/documents`)
        if (cancelled) return
        const completed = docs.filter((d) => d.processing_status === 'completed').length
        const processing = docs.filter((d) => d.processing_status === 'pending' || d.processing_status === 'processing').length
        attempts += 1
        if (processing > 0 && attempts >= MAX_DOC_POLL_ATTEMPTS) {
          // Give up waiting; surface the stalled document instead of spinning.
          setDocStats({ completed, processing: 0, total: docs.length })
          return
        }
        setDocStats({ completed, processing, total: docs.length })
        if (processing > 0) timer = setTimeout(poll, DOC_POLL_INTERVAL_MS)
      } catch {
        if (!cancelled) setDocStats({ completed: 0, processing: 0, total: 0 })
      }
    }
    poll()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [caseId, guidance])

  async function generate() {
    setLoading(true)
    setError('')
    try {
      const res = await api.post<SuggestedGuidanceResponse>(
        `/er/cases/${caseId}/guidance/suggested`,
      )
      onGuidanceChange(res)
      onGuidanceGenerated?.(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate guidance')
    } finally {
      setLoading(false)
    }
  }

  // Only ever auto-fetch EXISTING cached guidance (a cheap DB lookup) —
  // never call generate() just because the case was opened. Generating is a
  // real Gemini call and should only ever happen from an explicit "Get
  // Guidance" click, so simply viewing a case (open or closed) never kicks
  // off AI work on its own. The one exception is skipCache: the parent sets
  // it after a document upload, which is a genuine user action asking for
  // fresh guidance on the new evidence — but even then, never on a closed
  // case.
  useEffect(() => {
    if (guidance !== null) return
    if (docStats === null) return // wait for first document fetch
    if (loading) return
    if (isProcessing) return // show "processing" state; poll re-triggers this effect
    if (!hasReadyContent) return // genuine no-content → empty state in render

    if (skipCache) {
      onCacheSkipped?.()
      if (!isClosed) generate()
      return
    }

    if (hasFetchedCache.current) return // only ever check cache once per mount
    hasFetchedCache.current = true
    api.get<SuggestedGuidanceResponse>(`/er/cases/${caseId}/guidance/suggested`)
      .then((cached) => { if (cached) onGuidanceChange(cached) })
      .catch(() => { /* no cached guidance yet — user can click Get Guidance */ })
  }, [guidance, caseId, docStats, isProcessing, hasReadyContent, skipCache, isClosed]) // eslint-disable-line react-hooks/exhaustive-deps

  function streamOutcomes() {
    setOutcomeLoading(true)
    setOutcomeError('')
    setOutcomePhase('')
    setOutcomeData(null)
    setExpandedOutcomes(new Set())
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    postSSE(
      `/er/cases/${caseId}/guidance/outcomes/stream`,
      undefined,
      (data) => {
        const msg = data as { type?: string; message?: string; data?: OutcomeAnalysisResponse }
        if (msg.type === 'phase') setOutcomePhase(msg.message ?? '')
        if (msg.type === 'complete' || msg.type === 'result') {
          setOutcomeData(msg.data ?? null)
          return true
        }
      },
      { signal: ctrl.signal },
    )
      .catch((e) => {
        if (ctrl.signal.aborted) return
        setOutcomeError(e instanceof Error ? e.message : 'Failed to generate outcomes')
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setOutcomeLoading(false)
      })
  }

  function handleBeginDetermination() {
    setShowDetermination(true)
    streamOutcomes()
  }

  function toggleOutcomeExpand(idx: number) {
    setExpandedOutcomes((prev) => {
      const next = new Set(prev)
      next.has(idx) ? next.delete(idx) : next.add(idx)
      return next
    })
  }

  async function handleApplyOutcome(outcome: ERCaseOutcome, outcomeIdx: number) {
    if (!onBeginDetermination) return
    setApplying(outcome)
    const selectedOutcome = outcomeData?.outcomes?.[outcomeIdx]
    try {
      await onBeginDetermination(outcome, adminNotes[outcomeIdx] ?? '', selectedOutcome)
      setShowDetermination(false)
    } catch (e) {
      setOutcomeError(e instanceof Error ? e.message : 'Failed to apply outcome')
    } finally {
      setApplying(null)
    }
  }

  return {
    loading,
    error,
    determinationDismissed,
    setDeterminationDismissed,
    showDetermination,
    setShowDetermination,
    outcomeData,
    outcomeLoading,
    outcomePhase,
    outcomeError,
    applying,
    expandedOutcomes,
    adminNotes,
    setAdminNotes,
    abortRef,
    isClosed,
    docStats,
    totalDocs,
    isProcessing,
    hasReadyContent,
    generate,
    streamOutcomes,
    handleBeginDetermination,
    toggleOutcomeExpand,
    handleApplyOutcome,
  }
}
