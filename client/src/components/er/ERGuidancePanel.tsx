import { confidenceVariant, determinationVariant, priorityVariant } from '../ui/badgeMaps'
import { Badge, Button, LABEL } from '../ui'
import type { SuggestedGuidanceResponse, SuggestedGuidanceCard, ERCaseOutcome, OutcomeOption } from '../../types/er'
import { ComplianceGrounding } from './ComplianceGrounding'
import { useERGuidance } from './useERGuidance'


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
  const {
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
  } = useERGuidance({
    caseId,
    guidance,
    onGuidanceChange,
    onGuidanceGenerated,
    hasDescription,
    caseStatus,
    onBeginDetermination,
    skipCache,
    onCacheSkipped,
  })

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
