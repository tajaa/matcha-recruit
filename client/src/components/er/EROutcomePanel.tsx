import { useState, useRef } from 'react'
import { confidenceVariant, determinationVariant } from '../ui/badgeMaps'
import { api } from '../../api/client'
import { postSSE } from '../../api/sse'
import { Badge, Button } from '../ui'
import type { OutcomeAnalysisResponse, OutcomeOption, ERCaseOutcome } from '../../types/er'
import { ComplianceGrounding } from './ComplianceGrounding'




type Props = {
  caseId: string
  onApplyOutcome: (outcome: ERCaseOutcome) => Promise<void>
}

export function EROutcomePanel({ caseId, onApplyOutcome }: Props) {
  const [data, setData] = useState<OutcomeAnalysisResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [phase, setPhase] = useState('')
  const [error, setError] = useState('')
  const [applying, setApplying] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [adminNotes, setAdminNotes] = useState<Record<number, string>>({})
  const abortRef = useRef<AbortController | null>(null)

  function generate() {
    setLoading(true)
    setError('')
    setPhase('')
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    postSSE(
      `/er/cases/${caseId}/guidance/outcomes/stream`,
      undefined,
      (raw) => {
        const msg = raw as { type?: string; message?: string; data?: OutcomeAnalysisResponse }
        // Backend emits 'status'/'result'; older paths used 'phase'/'complete' — accept both.
        if (msg.type === 'phase' || msg.type === 'status') setPhase(msg.message ?? '')
        if (msg.type === 'complete' || msg.type === 'result') {
          setData(msg.data ?? null)
          return true
        }
      },
      { signal: ctrl.signal },
    )
      .catch((e) => {
        if (ctrl.signal.aborted) return
        setError(e instanceof Error ? e.message : 'Failed to generate outcomes')
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false)
      })
  }

  function toggleExpand(idx: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(idx) ? next.delete(idx) : next.add(idx)
      return next
    })
  }

  async function handleApply(outcome: ERCaseOutcome, outcomeIdx: number) {
    setApplying(outcome)
    try {
      await api.put(`/er/cases/${caseId}`, { outcome, status: 'closed' })
      const notes = adminNotes[outcomeIdx]?.trim()
      if (notes) {
        await api.post(`/er/cases/${caseId}/notes`, {
          note_type: 'system',
          content: `Determination notes: ${notes}`,
          metadata: { source: 'determination', note_purpose: 'admin_notes' },
        })
      }
      await onApplyOutcome(outcome)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to apply outcome')
    } finally {
      setApplying(null)
    }
  }

  if (loading) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-zinc-500">{phase || 'Generating outcome analysis...'}</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-zinc-500 mb-2">
          Generate AI-powered outcome recommendations based on evidence, policy, and precedent.
        </p>
        <p className="text-xs text-zinc-600 mb-4">This analysis is resource-intensive and user-initiated only.</p>
        <Button onClick={generate}>Generate Outcome Analysis</Button>
        {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Case summary */}
      {data.case_summary && (
        <div className="rounded-lg bg-zinc-900/50 border border-zinc-800 px-4 py-3">
          <p className="text-sm text-zinc-300">{data.case_summary}</p>
        </div>
      )}

      <ComplianceGrounding citations={data.compliance_citations} />

      {/* Outcome option cards */}
      {data.outcomes.map((opt: OutcomeOption, i: number) => (
        <div key={i} className="border border-zinc-800 rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={determinationVariant[opt.determination] ?? 'neutral'}>
              {opt.determination}
            </Badge>
            <span className="text-sm font-medium text-zinc-100">{opt.action_label}</span>
            <Badge variant={confidenceVariant[opt.confidence] ?? 'neutral'}>
              {opt.confidence} confidence
            </Badge>
          </div>

          {/* Expandable sections */}
          <button
            type="button"
            className="text-xs px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-500 transition-colors"
            onClick={() => toggleExpand(i)}
          >
            {expanded.has(i) ? '▾ Hide details' : '▸ Show details'}
          </button>

          {expanded.has(i) && (
            <div className="space-y-3 border-l-2 border-zinc-700 pl-3">
              <div>
                <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Reasoning</p>
                <p className="text-sm text-zinc-300 leading-relaxed">{opt.reasoning}</p>
              </div>
              <div>
                <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">Policy Basis</p>
                <p className="text-sm text-zinc-300 leading-relaxed">{opt.policy_basis}</p>
              </div>
              <div>
                <p className="text-[11px] text-zinc-500 uppercase tracking-wide mb-1">HR Considerations</p>
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
            onClick={() => handleApply(opt.recommended_action, i)}
          >
            {applying === opt.recommended_action ? 'Applying...' : 'Apply This Outcome'}
          </Button>
        </div>
      ))}

      <div className="flex justify-end">
        <Button variant="ghost" size="sm" onClick={generate}>Regenerate</Button>
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  )
}
