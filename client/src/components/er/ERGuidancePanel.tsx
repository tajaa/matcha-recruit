import { useState, useEffect, useRef } from 'react'
import { api } from '../../api/client'
import { postSSE } from '../../api/sse'
import { Badge, Button, LABEL, type BadgeVariant } from '../ui'
import type { SuggestedGuidanceResponse, SuggestedGuidanceCard, ERCaseOutcome, OutcomeOption, OutcomeAnalysisResponse, ERDocument } from '../../types/er'
import { ComplianceGrounding } from './ComplianceGrounding'


// Document-processing poll cadence. The cap (~45s) bounds the wait for a
// document that never finishes parsing; the server-side sweep marks such rows
// 'failed' within 15 min, so this always gives up well ahead of that.
const DOC_POLL_INTERVAL_MS = 3000
const MAX_DOC_POLL_ATTEMPTS = 15

const priorityVariant: Record<string, BadgeVariant> = {
  high: 'danger',
  medium: 'warning',
  low: 'neutral',
}

const determinationVariant: Record<string, BadgeVariant> = {
  substantiated: 'danger',
  unsubstantiated: 'success',
  inconclusive: 'warning',
}

const confidenceVariant: Record<string, BadgeVariant> = {
  high: 'success',
  medium: 'warning',
  low: 'neutral',
}

type ERGuidancePanelProps = {
  caseId: string
  guidance: SuggestedGuidanceResponse | null
  onGuidanceChange: (g: SuggestedGuidanceResponse | null) => void
  onGuidanceGenerated?: (g: SuggestedGuidanceResponse) => void
  documentCount: number
  hasDescription: boolean
  caseStatus?: string
  onActionClick?: (action: {
    type: string
    label: string
    tab?: string | null
    analysis_type?: string | null
    search_query?: string | null
  }) => void
  onBeginDetermination?: (outcome: ERCaseOutcome, adminNotes: string, outcomeDetail?: OutcomeOption) => Promise<void>
  skipCache?: boolean
  onCacheSkipped?: () => void
}

export function ERGuidancePanel({ caseId, guidance, onGuidanceChange, onGuidanceGenerated, hasDescription, caseStatus, onActionClick, onBeginDetermination, skipCache, onCacheSkipped }: ERGuidancePanelProps) {
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

  if (!guidance && !loading) {
    // First document fetch still in flight — avoid flashing the empty state.
    if (docStats === null) {
      return <p className="text-sm text-zinc-500 py-8 text-center">Loading...</p>
    }
    // A document was uploaded (e.g. at intake) and is still parsing — wait for it
    // rather than nagging the user to upload a complaint.
    if (isProcessing) {
      return (
        <p className="text-sm text-zinc-500 py-8 text-center">
          Processing your documents… guidance will appear once parsing finishes.
        </p>
      )
    }
    if (!hasReadyContent) {
      return (
        <div className="text-center py-8">
          <p className="text-sm text-zinc-500">
            {totalDocs > 0
              ? 'Document processing did not complete. Re-upload on the Documents tab, or add a case description.'
              : 'Upload documents or add a case description before generating guidance.'}
          </p>
        </div>
      )
    }
    return (
      <div className="text-center py-8">
        <p className="text-sm text-zinc-500 mb-4">
          {error ? 'Guidance generation failed. You can try again.' : 'Generate AI-powered guidance for this case based on uploaded documents and notes.'}
        </p>
        <Button onClick={generate}>Get Guidance</Button>
        {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
      </div>
    )
  }

  if (loading) {
    return <p className="text-sm text-zinc-500 py-8 text-center">Analyzing case...</p>
  }

  if (!guidance) return null

  return (
    <div className="space-y-4">
      <div className="rounded-lg bg-zinc-900/50 border border-white/[0.08] px-4 py-3">
        <p className="text-sm text-zinc-300">{guidance.summary}</p>
      </div>

      <ComplianceGrounding citations={guidance.compliance_citations} />

      {/* Preponderance of evidence threshold banner */}
      {guidance.determination_suggested && !determinationDismissed && !showDetermination && !isClosed && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-4 py-4">
          <div className="flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-emerald-300">Sufficient Evidence to Determine</p>
              <p className="text-xs text-emerald-400/70 mt-1 leading-relaxed">
                Evidence confidence at {Math.round(guidance.determination_confidence * 100)}% — the investigation
                has gathered sufficient material to support a case determination. Individual outcome options reflect
                how clearly the evidence points to each specific path.
              </p>
              {guidance.determination_signals.length > 0 && (
                <ul className="mt-2 space-y-0.5">
                  {guidance.determination_signals.map((signal, i) => (
                    <li key={i} className="text-[11px] text-emerald-400/60">- {signal}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 mt-3">
            <Button size="sm" onClick={handleBeginDetermination}>
              Begin Case Determination
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setDeterminationDismissed(true)}>
              Continue Investigating
            </Button>
          </div>
        </div>
      )}

      {/* Inline AI-powered determination */}
      {showDetermination && !isClosed && (
        <div className="rounded-lg border border-white/[0.08] bg-zinc-900/60 px-4 py-4 space-y-4">
          <div>
            <p className="text-sm font-medium text-zinc-200 mb-1">Case Determination</p>
            <p className="text-xs text-zinc-500">AI-ranked outcome recommendations based on evidence, policy, and precedent.</p>
          </div>

          {outcomeLoading && (
            <div className="text-center py-4">
              <p className="text-sm text-zinc-500">{outcomePhase || 'Generating outcome analysis...'}</p>
            </div>
          )}

          {outcomeError && <p className="text-xs text-red-400">{outcomeError}</p>}

          {!outcomeLoading && !outcomeData && !outcomeError && (
            <div className="text-center py-4">
              <p className="text-sm text-zinc-500 mb-2">No outcome data was returned. Try again.</p>
              <Button size="sm" onClick={streamOutcomes}>Retry</Button>
            </div>
          )}

          {outcomeData && (outcomeData.outcomes ?? []).map((opt: OutcomeOption, i: number) => (
            <div key={i} className="border border-white/[0.08] rounded-lg p-3 space-y-2">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant={determinationVariant[opt.determination] ?? 'neutral'}>
                  {opt.determination}
                </Badge>
                <span className="text-sm font-medium text-zinc-100">{opt.action_label}</span>
                <Badge variant={confidenceVariant[opt.confidence] ?? 'neutral'}>
                  {opt.confidence} confidence
                </Badge>
              </div>

              <button
                type="button"
                className="text-xs px-2 py-1 rounded border border-white/[0.08] text-zinc-400 hover:text-zinc-200 hover:border-emerald-500/40 transition-colors"
                onClick={() => toggleOutcomeExpand(i)}
              >
                {expandedOutcomes.has(i) ? '▾ Hide details' : '▸ Show details'}
              </button>

              {expandedOutcomes.has(i) && (
                <div className="space-y-2 border-l-2 border-emerald-500/30 pl-3">
                  <div>
                    <p className={`${LABEL} mb-0.5`}>Reasoning</p>
                    <p className="text-sm text-zinc-300 leading-relaxed">{opt.reasoning}</p>
                  </div>
                  <div>
                    <p className={`${LABEL} mb-0.5`}>Policy Basis</p>
                    <p className="text-sm text-zinc-300 leading-relaxed">{opt.policy_basis}</p>
                  </div>
                  <div>
                    <p className={`${LABEL} mb-0.5`}>HR Considerations</p>
                    <p className="text-sm text-zinc-300 leading-relaxed">{opt.hr_considerations}</p>
                  </div>
                  {opt.party_actions && opt.party_actions.length > 0 && (
                    <div>
                      <p className={`${LABEL} mb-1`}>Actions by Party</p>
                      <div className="space-y-1.5">
                        {opt.party_actions.map((pa, j) => (
                          <div key={j} className="text-sm">
                            <span className="font-medium text-zinc-200">{pa.name}</span>
                            <span className="text-zinc-500"> ({pa.role})</span>
                            <span className="text-zinc-400"> — {pa.action}</span>
                            {pa.detail && <p className="text-xs text-zinc-500 mt-0.5">{pa.detail}</p>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {opt.precedent_note && (
                <p className="text-xs text-zinc-500 italic">{opt.precedent_note}</p>
              )}

              <div className="space-y-1.5 pt-1">
                <p className={LABEL}>Admin Notes</p>
                <textarea
                  value={adminNotes[i] ?? ''}
                  onChange={(e) => setAdminNotes((prev) => ({ ...prev, [i]: e.target.value }))}
                  placeholder="Add notes before closing this case..."
                  rows={2}
                  className="w-full bg-zinc-900 border border-white/[0.08] rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-emerald-500/50 resize-none"
                />
              </div>

              <Button
                size="sm"
                disabled={applying !== null}
                onClick={() => handleApplyOutcome(opt.recommended_action, i)}
              >
                {applying === opt.recommended_action ? 'Applying...' : 'Apply This Outcome'}
              </Button>
            </div>
          ))}

          <div className="flex items-center gap-2">
            {outcomeData && (
              <Button variant="ghost" size="sm" onClick={streamOutcomes}>Regenerate</Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => { abortRef.current?.abort(); setShowDetermination(false) }}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Closed case banner */}
      {isClosed && (
        <div className="rounded-lg border border-white/[0.08] bg-zinc-900/30 px-4 py-3">
          <p className="text-sm text-zinc-400">This case has been closed. Review the Notes tab for determination details.</p>
        </div>
      )}

      {/* Confidence meter (when below threshold) */}
      {!isClosed && !guidance.determination_suggested && guidance.determination_confidence > 0 && (
        <div className="rounded-lg border border-white/[0.08] bg-zinc-900/30 px-4 py-3">
          <div className="flex items-center justify-between mb-1.5">
            <span className={LABEL}>Evidence Confidence</span>
            <span className="font-mono text-[11px] tabular-nums text-zinc-400">{Math.round(guidance.determination_confidence * 100)}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${guidance.determination_confidence >= 0.5 ? 'bg-amber-400' : 'bg-zinc-600'}`}
              style={{ width: `${Math.round(guidance.determination_confidence * 100)}%` }}
            />
          </div>
          <p className="text-[11px] text-zinc-600 mt-1">Preponderance threshold: 80%</p>
        </div>
      )}

      {guidance.cards.length > 0 && (
        <div className="space-y-3">
          {guidance.cards.map((card: SuggestedGuidanceCard) => (
            <div key={card.id} className="rounded-lg border border-white/[0.08] bg-zinc-900 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-zinc-100">{card.title}</span>
                    <Badge variant={priorityVariant[card.priority] ?? 'neutral'}>
                      {card.priority}
                    </Badge>
                  </div>
                  <p className="text-xs text-zinc-400">{card.recommendation}</p>
                  {card.rationale && (
                    <p className="text-xs text-zinc-500 mt-1 italic">{card.rationale}</p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onActionClick?.({
                    type: card.action.type,
                    label: card.action.label,
                    tab: card.action.tab,
                    analysis_type: card.action.analysis_type,
                    search_query: card.action.search_query,
                  })}
                >
                  {card.action.label}
                </Button>
              </div>

              {card.interview_questions && card.interview_questions.length > 0 && (
                <div className="mt-3 border-l-2 border-amber-500/30 pl-3">
                  <p className="text-[10px] font-medium uppercase tracking-[0.15em] text-amber-400/80 mb-1.5">
                    Suggested questions
                  </p>
                  <ol className="list-decimal pl-4 space-y-1 text-xs text-zinc-300">
                    {card.interview_questions.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex justify-end">
        <Button variant="ghost" size="sm" onClick={generate}>
          Regenerate
        </Button>
      </div>
    </div>
  )
}
