import { Loader2, Check } from 'lucide-react'
import { Button, Badge } from '../ui'

export type CopilotCardAction = {
  type: 'run_analysis' | 'set_field' | 'request_info' | 'escalate' | 'close_incident'
  label: string
  tab?: string | null
  analysis_type?: string | null
  field_name?: string | null
  field_value?: string | null
  search_query?: string | null
}

export type CopilotCard = {
  id: string
  title: string
  recommendation: string
  rationale: string
  priority: 'high' | 'medium' | 'low'
  blockers: string[]
  action: CopilotCardAction
  interview_questions?: string[] | null
}

const PRIORITY_VARIANT: Record<string, 'danger' | 'warning' | 'neutral'> = {
  high: 'danger',
  medium: 'warning',
  low: 'neutral',
}

const PRIORITY_LABEL: Record<string, string> = {
  high: 'HIGH',
  medium: 'MED',
  low: 'LOW',
}

interface Props {
  messageId: string
  card: CopilotCard
  accepted: boolean
  busy: boolean
  onAccept: (messageId: string, cardId: string) => void
  onSkip: (messageId: string) => void
}

export default function IRCopilotCard({ messageId, card, accepted, busy, onAccept, onSkip }: Props) {
  return (
    <div
      className={`rounded-lg border p-4 ${
        accepted ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-zinc-700 bg-zinc-900'
      }`}
    >
      <div className="flex items-start gap-3">
        <Badge variant={PRIORITY_VARIANT[card.priority] || 'neutral'}>
          {PRIORITY_LABEL[card.priority] || 'MED'}
        </Badge>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-zinc-100">{card.title}</h4>
          <p className="text-sm text-zinc-300 mt-1">{card.recommendation}</p>
          <p className="text-xs text-zinc-500 mt-1.5">{card.rationale}</p>

          {card.blockers && card.blockers.length > 0 && (
            <div className="mt-2 text-xs text-amber-400">
              Blockers: {card.blockers.join(' · ')}
            </div>
          )}

          {card.interview_questions && card.interview_questions.length > 0 && (
            <div className="mt-3 border-l-2 border-zinc-700 pl-3">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">
                Suggested questions
              </div>
              <ul className="text-xs text-zinc-300 space-y-0.5 list-disc pl-4">
                {card.interview_questions.slice(0, 5).map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-3 flex items-center gap-2">
            {accepted ? (
              <div className="flex items-center gap-1 text-emerald-400 text-xs">
                <Check className="w-3 h-3" /> Done
              </div>
            ) : (
              <>
                <Button
                  size="sm"
                  variant="primary"
                  disabled={busy}
                  onClick={() => onAccept(messageId, card.id)}
                >
                  {busy ? (
                    <span className="flex items-center gap-1">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      Working…
                    </span>
                  ) : (
                    card.action.label || 'Accept'
                  )}
                </Button>
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => onSkip(messageId)}>
                  Skip
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
