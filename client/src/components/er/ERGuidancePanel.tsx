import { useState } from 'react'
import { api } from '../../api/client'
import { Badge, Button, Card, type BadgeVariant } from '../ui'
import type { SuggestedGuidanceResponse, SuggestedGuidanceCard } from '../../types/er'

const priorityVariant: Record<string, BadgeVariant> = {
  high: 'danger',
  medium: 'warning',
  low: 'neutral',
}

type ERGuidancePanelProps = {
  caseId: string
  onActionClick?: (action: { type: string; label: string }) => void
}

export function ERGuidancePanel({ caseId, onActionClick }: ERGuidancePanelProps) {
  const [guidance, setGuidance] = useState<SuggestedGuidanceResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function generate() {
    setLoading(true)
    setError('')
    try {
      const res = await api.post<SuggestedGuidanceResponse>(
        `/er/cases/${caseId}/guidance/suggested`,
      )
      setGuidance(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate guidance')
    } finally {
      setLoading(false)
    }
  }

  if (!guidance && !loading) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-zinc-500 mb-4">
          Generate AI-powered guidance for this case based on uploaded documents and notes.
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

      {guidance.determination_signals.length > 0 && (
        <div className="rounded-lg border border-zinc-800 px-4 py-3">
          <p className="text-xs font-medium text-zinc-400 mb-2">Determination Signals</p>
          <ul className="space-y-1">
            {guidance.determination_signals.map((signal, i) => (
              <li key={i} className="text-xs text-zinc-500">- {signal}</li>
            ))}
          </ul>
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
