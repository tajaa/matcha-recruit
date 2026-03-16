import { useState, useRef } from 'react'
import { api } from '../../api/client'
import { Badge, Button, type BadgeVariant } from '../ui'
import type { OutcomeAnalysisResponse, OutcomeOption, ERCaseOutcome } from '../../types/er'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

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
  const abortRef = useRef<AbortController | null>(null)

  function generate() {
    setLoading(true)
    setError('')
    setPhase('')
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
            if (raw === '[DONE]') { setLoading(false); return }
            try {
              const msg = JSON.parse(raw)
              if (msg.type === 'phase') setPhase(msg.message ?? '')
              if (msg.type === 'complete') { setData(msg.data); setLoading(false); return }
            } catch { /* skip malformed */ }
          }
        }
        setLoading(false)
      })
      .catch((e) => {
        if (e.name !== 'AbortError') {
          setError(e instanceof Error ? e.message : 'Failed to generate outcomes')
          setLoading(false)
        }
      })
  }

  function toggleExpand(idx: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(idx) ? next.delete(idx) : next.add(idx)
      return next
    })
  }

  async function handleApply(outcome: ERCaseOutcome) {
    setApplying(outcome)
    try {
      await api.put(`/er/cases/${caseId}`, { outcome, status: 'pending_determination' })
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
            className="text-xs text-zinc-500 hover:text-zinc-300 cursor-pointer"
            onClick={() => toggleExpand(i)}
          >
            {expanded.has(i) ? 'Hide details' : 'Show details'}
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

          <Button
            size="sm"
            disabled={applying !== null}
            onClick={() => handleApply(opt.recommended_action)}
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
