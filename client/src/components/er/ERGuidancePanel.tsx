import { useState, useEffect, useRef } from 'react'
import { api } from '../../api/client'
import { Badge, Button, Card, Select, type BadgeVariant } from '../ui'
import type { SuggestedGuidanceResponse, SuggestedGuidanceCard, ERCaseOutcome } from '../../types/er'
import { outcomeLabel } from '../../types/er'

const priorityVariant: Record<string, BadgeVariant> = {
  high: 'danger',
  medium: 'warning',
  low: 'neutral',
}

const OUTCOME_OPTIONS = [
  { value: '', label: 'Select outcome...' },
  { value: 'termination', label: outcomeLabel.termination },
  { value: 'disciplinary_action', label: outcomeLabel.disciplinary_action },
  { value: 'retraining', label: outcomeLabel.retraining },
  { value: 'no_action', label: outcomeLabel.no_action },
  { value: 'resignation', label: outcomeLabel.resignation },
  { value: 'other', label: outcomeLabel.other },
]

type ERGuidancePanelProps = {
  caseId: string
  guidance: SuggestedGuidanceResponse | null
  onGuidanceChange: (g: SuggestedGuidanceResponse | null) => void
  onActionClick?: (action: { type: string; label: string }) => void
  onBeginDetermination?: (outcome: ERCaseOutcome) => Promise<void>
}

export function ERGuidancePanel({ caseId, guidance, onGuidanceChange, onActionClick, onBeginDetermination }: ERGuidancePanelProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [determinationDismissed, setDeterminationDismissed] = useState(false)
  const [showDetermination, setShowDetermination] = useState(false)
  const [selectedOutcome, setSelectedOutcome] = useState<string>('')
  const [closingCase, setClosingCase] = useState(false)

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
  }, [guidance, caseId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleCloseCase() {
    if (!selectedOutcome || !onBeginDetermination) return
    setClosingCase(true)
    try {
      await onBeginDetermination(selectedOutcome as ERCaseOutcome)
    } finally {
      setClosingCase(false)
      setShowDetermination(false)
    }
  }

  if (!guidance && !loading) {
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
      {guidance.determination_suggested && !determinationDismissed && !showDetermination && (
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
            <Button size="sm" onClick={() => setShowDetermination(true)}>
              Begin Case Determination
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setDeterminationDismissed(true)}>
              Continue Investigating
            </Button>
          </div>
        </div>
      )}

      {/* Inline determination form */}
      {showDetermination && (
        <div className="rounded-lg border border-zinc-700 bg-zinc-900/60 px-4 py-4 space-y-4">
          <div>
            <p className="text-sm font-medium text-zinc-200 mb-1">Close Case with Outcome</p>
            <p className="text-xs text-zinc-500">Select the determination outcome and close this case.</p>
          </div>
          <Select
            label="Outcome"
            options={OUTCOME_OPTIONS}
            value={selectedOutcome}
            onChange={(e) => setSelectedOutcome(e.target.value)}
          />
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              disabled={!selectedOutcome || closingCase}
              onClick={handleCloseCase}
            >
              {closingCase ? 'Closing...' : 'Close Case'}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setShowDetermination(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Confidence meter (when below threshold) */}
      {!guidance.determination_suggested && guidance.determination_confidence > 0 && (
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
