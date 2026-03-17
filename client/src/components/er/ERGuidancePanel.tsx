import { useState, useEffect, useRef } from 'react'
import { api } from '../../api/client'
import { Badge, Button, Card, type BadgeVariant } from '../ui'
import type { SuggestedGuidanceResponse, SuggestedGuidanceCard, ERCaseOutcome, OutcomeOption, OutcomeAnalysisResponse } from '../../types/er'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

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
  onActionClick?: (action: { type: string; label: string }) => void
  onBeginDetermination?: (outcome: ERCaseOutcome, adminNotes: string) => Promise<void>
}

export function ERGuidancePanel({ caseId, guidance, onGuidanceChange, onGuidanceGenerated, documentCount, hasDescription, caseStatus, onActionClick, onBeginDetermination }: ERGuidancePanelProps) {
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

  const hasContent = documentCount > 0 || hasDescription

  // Tracks whether we've already done the initial cache-fetch on this mount.
  // Distinguishes "first mount with no guidance" (→ try cache first)
  // from "guidance cleared by parent after upload" (→ regenerate directly).
  const hasFetchedCache = useRef(false)

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

  // On mount (or caseId change): try cached guidance first.
  // If guidance is already in parent state, skip.
  // If guidance is null and we've already fetched cache once (invalidation path), regenerate directly.
  useEffect(() => {
    if (guidance !== null) return
    if (!hasContent) return

    if (hasFetchedCache.current) {
      // Parent cleared guidance (e.g. after document upload) — regenerate
      generate()
      return
    }

    hasFetchedCache.current = true
    api.get<SuggestedGuidanceResponse>(`/er/cases/${caseId}/guidance/suggested`)
      .then((cached) => {
        if (cached) {
          onGuidanceChange(cached)
        } else {
          generate() // 204 empty response → generate fresh
        }
      })
      .catch(() => generate()) // error → generate fresh
  }, [guidance, caseId, hasContent]) // eslint-disable-line react-hooks/exhaustive-deps

  function streamOutcomes() {
    setOutcomeLoading(true)
    setOutcomeError('')
    setOutcomePhase('')
    setOutcomeData(null)
    setExpandedOutcomes(new Set())
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    const token = localStorage.getItem('matcha_access_token')

    fetch(`${BASE}/er/cases/${caseId}/guidance/outcomes/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      signal: ctrl.signal,
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
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
            const raw = line.slice(6).trim()
            if (raw === '[DONE]') { setOutcomeLoading(false); return }
            try {
              const msg = JSON.parse(raw)
              if (msg.type === 'phase') setOutcomePhase(msg.message ?? '')
              if (msg.type === 'complete' || msg.type === 'result') { setOutcomeData(msg.data); setOutcomeLoading(false); return }
            } catch { /* skip malformed */ }
          }
        }
        setOutcomeLoading(false)
      })
      .catch((e) => {
        if (e.name !== 'AbortError') {
          setOutcomeError(e instanceof Error ? e.message : 'Failed to generate outcomes')
          setOutcomeLoading(false)
        }
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
    try {
      await onBeginDetermination(outcome, adminNotes[outcomeIdx] ?? '')
      setShowDetermination(false)
    } catch (e) {
      setOutcomeError(e instanceof Error ? e.message : 'Failed to apply outcome')
    } finally {
      setApplying(null)
    }
  }

  if (!guidance && !loading) {
    if (!hasContent) {
      return (
        <div className="text-center py-8">
          <p className="text-sm text-zinc-500">
            Upload documents or add a case description before generating guidance.
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
      <div className="rounded-lg bg-zinc-900/50 border border-zinc-800 px-4 py-3">
        <p className="text-sm text-zinc-300">{guidance.summary}</p>
      </div>

      {/* Preponderance of evidence threshold banner */}
      {guidance.determination_suggested && !determinationDismissed && !showDetermination && !isClosed && (
        <div className="rounded-lg border border-emerald-800/60 bg-emerald-950/30 px-4 py-4">
          <div className="flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-emerald-300">Preponderance of Evidence Reached</p>
              <p className="text-xs text-emerald-400/70 mt-1 leading-relaxed">
                Based on the evidence gathered ({Math.round(guidance.determination_confidence * 100)}% confidence),
                this case has reached the preponderance of evidence threshold.
                You can begin generating case determination options or continue investigating to strengthen the record.
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
        <div className="rounded-lg border border-zinc-700 bg-zinc-900/60 px-4 py-4 space-y-4">
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
            <div key={i} className="border border-zinc-800 rounded-lg p-3 space-y-2">
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
                className="text-xs px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-500 transition-colors"
                onClick={() => toggleOutcomeExpand(i)}
              >
                {expandedOutcomes.has(i) ? '▾ Hide details' : '▸ Show details'}
              </button>

              {expandedOutcomes.has(i) && (
                <div className="space-y-2 border-l-2 border-zinc-700 pl-3">
                  <div>
                    <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-0.5">Reasoning</p>
                    <p className="text-sm text-zinc-300 leading-relaxed">{opt.reasoning}</p>
                  </div>
                  <div>
                    <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-0.5">Policy Basis</p>
                    <p className="text-sm text-zinc-300 leading-relaxed">{opt.policy_basis}</p>
                  </div>
                  <div>
                    <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-0.5">HR Considerations</p>
                    <p className="text-sm text-zinc-300 leading-relaxed">{opt.hr_considerations}</p>
                  </div>
                </div>
              )}

              {opt.precedent_note && (
                <p className="text-xs text-zinc-500 italic">{opt.precedent_note}</p>
              )}

              <div className="space-y-1.5 pt-1">
                <p className="text-[11px] text-zinc-500 uppercase tracking-wide">Admin Notes</p>
                <textarea
                  value={adminNotes[i] ?? ''}
                  onChange={(e) => setAdminNotes((prev) => ({ ...prev, [i]: e.target.value }))}
                  placeholder="Add notes before closing this case..."
                  rows={2}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500 resize-none"
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
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 px-4 py-3">
          <p className="text-sm text-zinc-400">This case has been closed. Review the Notes tab for determination details.</p>
        </div>
      )}

      {/* Confidence meter (when below threshold) */}
      {!isClosed && !guidance.determination_suggested && guidance.determination_confidence > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 px-4 py-3">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] text-zinc-500 uppercase tracking-wide">Evidence Confidence</span>
            <span className="text-[11px] font-mono text-zinc-400">{Math.round(guidance.determination_confidence * 100)}%</span>
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
            <Card key={card.id} className="p-4">
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
                  onClick={() => onActionClick?.({ type: card.action.type, label: card.action.label })}
                >
                  {card.action.label}
                </Button>
              </div>
            </Card>
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
