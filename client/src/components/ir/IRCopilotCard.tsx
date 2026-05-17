import { useState } from 'react'
import { Loader2, Check, Phone, AlertOctagon } from 'lucide-react'
import { Button, Badge } from '../ui'

export type CopilotCardActionType =
  | 'run_analysis'
  | 'set_field'
  | 'request_info'
  | 'escalate'
  | 'close_incident'
  | 'quick_reply'
  | 'numeric_input'
  | 'text_input'
  | 'osha_emergency_alert'

export type CopilotCardChoice = {
  label: string
  value: string
}

export type CopilotCardAction = {
  type: CopilotCardActionType
  label: string
  tab?: string | null
  analysis_type?: string | null
  field_name?: string | null
  field_value?: string | null
  search_query?: string | null
  // quick_reply: button picker.
  choices?: CopilotCardChoice[]
  quick_reply_kind?: string
  // numeric_input / text_input: validated input field.
  target_field?: string
  pending_classification?: string
  input_label?: string
  input_min?: number
  input_max?: number
  prompt_text?: string
  input_rows?: number
  // osha_emergency_alert: informational + acknowledgment.
  phone?: string
  deadline?: string
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

export type AcceptPayload = {
  selected_value?: string
  numeric_value?: number
  text_value?: string
  notes?: string
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
  onAccept: (messageId: string, cardId: string, payload?: AcceptPayload) => void
  onSkip: (messageId: string) => void
}

export default function IRCopilotCard({ messageId, card, accepted, busy, onAccept, onSkip }: Props) {
  // OSHA emergency alert renders as a distinct red blocking card with a
  // phone link and a required-notes textarea before the user can clear it.
  if (card.action.type === 'osha_emergency_alert') {
    return (
      <OshaEmergencyAlertCard
        messageId={messageId}
        card={card}
        accepted={accepted}
        busy={busy}
        onAccept={onAccept}
      />
    )
  }

  const isQuickReply = card.action.type === 'quick_reply' && Array.isArray(card.action.choices)
  const isNumericInput = card.action.type === 'numeric_input'
  const isTextInput = card.action.type === 'text_input'

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

          <div className="mt-3 flex items-center gap-2 flex-wrap">
            {accepted ? (
              <div className="flex items-center gap-1 text-emerald-400 text-xs">
                <Check className="w-3 h-3" /> Done
              </div>
            ) : isQuickReply ? (
              <QuickReplyButtons
                messageId={messageId}
                card={card}
                busy={busy}
                onAccept={onAccept}
              />
            ) : isNumericInput ? (
              <NumericInputControl
                messageId={messageId}
                card={card}
                busy={busy}
                onAccept={onAccept}
              />
            ) : isTextInput ? (
              <TextInputControl
                messageId={messageId}
                card={card}
                busy={busy}
                onAccept={onAccept}
              />
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

function QuickReplyButtons({
  messageId,
  card,
  busy,
  onAccept,
}: {
  messageId: string
  card: CopilotCard
  busy: boolean
  onAccept: (messageId: string, cardId: string, payload?: AcceptPayload) => void
}) {
  const choices = card.action.choices || []
  return (
    <>
      {choices.map((c) => (
        <Button
          key={c.value}
          size="sm"
          variant="primary"
          disabled={busy}
          onClick={() => onAccept(messageId, card.id, { selected_value: c.value })}
        >
          {busy ? (
            <span className="flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" />
              {c.label}
            </span>
          ) : (
            c.label
          )}
        </Button>
      ))}
    </>
  )
}

function NumericInputControl({
  messageId,
  card,
  busy,
  onAccept,
}: {
  messageId: string
  card: CopilotCard
  busy: boolean
  onAccept: (messageId: string, cardId: string, payload?: AcceptPayload) => void
}) {
  const [value, setValue] = useState('')
  const min = card.action.input_min ?? 1
  const max = card.action.input_max ?? 365
  const parsed = parseInt(value, 10)
  const valid = !Number.isNaN(parsed) && parsed >= min && parsed <= max
  return (
    <div className="flex items-center gap-2 w-full">
      <label className="text-xs text-zinc-400">{card.action.input_label || 'Value'}</label>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        disabled={busy}
        onChange={(e) => setValue(e.target.value)}
        className="w-24 rounded-md bg-zinc-950 border border-zinc-700 px-2 py-1 text-sm text-zinc-100 outline-none focus:border-emerald-500"
      />
      <Button
        size="sm"
        variant="primary"
        disabled={busy || !valid}
        onClick={() => onAccept(messageId, card.id, { numeric_value: parsed })}
      >
        {busy ? (
          <span className="flex items-center gap-1">
            <Loader2 className="w-3 h-3 animate-spin" />
            Saving…
          </span>
        ) : (
          card.action.label || 'Save'
        )}
      </Button>
      {!valid && value !== '' && (
        <span className="text-[11px] text-amber-400">Range {min}-{max}</span>
      )}
    </div>
  )
}

function TextInputControl({
  messageId,
  card,
  busy,
  onAccept,
}: {
  messageId: string
  card: CopilotCard
  busy: boolean
  onAccept: (messageId: string, cardId: string, payload?: AcceptPayload) => void
}) {
  const [value, setValue] = useState('')
  const rows = card.action.input_rows ?? 3
  const valid = value.trim().length > 0
  return (
    <div className="flex flex-col gap-2 w-full">
      {card.action.prompt_text && (
        <label className="text-xs text-zinc-400">{card.action.prompt_text}</label>
      )}
      <textarea
        rows={rows}
        maxLength={4000}
        value={value}
        disabled={busy}
        placeholder="Type your answer…"
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && valid && !busy) {
            e.preventDefault()
            onAccept(messageId, card.id, { text_value: value.trim() })
          }
        }}
        className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500 resize-y"
      />
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          disabled={busy || !valid}
          onClick={() => onAccept(messageId, card.id, { text_value: value.trim() })}
        >
          {busy ? (
            <span className="flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" />
              Saving…
            </span>
          ) : (
            card.action.label || 'Save'
          )}
        </Button>
        <span className="text-[11px] text-zinc-500">⌘+Enter to save</span>
      </div>
    </div>
  )
}


function OshaEmergencyAlertCard({
  messageId,
  card,
  accepted,
  busy,
  onAccept,
}: {
  messageId: string
  card: CopilotCard
  accepted: boolean
  busy: boolean
  onAccept: (messageId: string, cardId: string, payload?: AcceptPayload) => void
}) {
  const [notes, setNotes] = useState('')
  const phone = card.action.phone || '1-800-321-6742'
  const deadline = card.action.deadline || '8 to 24 hours'
  if (accepted) {
    return (
      <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 flex items-center gap-2 text-sm text-emerald-300">
        <Check className="w-4 h-4" />
        OSHA reporting alert acknowledged.
      </div>
    )
  }
  return (
    <div className="rounded-lg border-2 border-red-500/60 bg-red-500/10 p-4">
      <div className="flex items-start gap-3">
        <AlertOctagon className="w-6 h-6 text-red-400 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-semibold text-red-200 uppercase tracking-wider">
            {card.title}
          </h4>
          <p className="text-sm text-zinc-100 mt-2">{card.recommendation}</p>
          <p className="text-xs text-zinc-300 mt-1.5">{card.rationale}</p>

          <div className="mt-3 rounded-md bg-zinc-950/50 border border-red-500/30 px-3 py-2.5">
            <div className="text-[10px] uppercase tracking-wider text-red-300 mb-1">
              Call OSHA directly · within {deadline}
            </div>
            <a
              href={`tel:${phone.replace(/[^\d+]/g, '')}`}
              className="text-base font-semibold text-red-200 flex items-center gap-2 hover:underline"
            >
              <Phone className="w-4 h-4" />
              {phone}
            </a>
          </div>

          <div className="mt-3">
            <label className="text-[11px] uppercase tracking-wider text-zinc-400 mb-1 block">
              Confirm reporting notes (required)
            </label>
            <textarea
              value={notes}
              disabled={busy}
              placeholder="e.g. Called OSHA at 14:30. Case #XXXX. Spoke to inspector Jones."
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="w-full rounded-md bg-zinc-950 border border-zinc-700 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-emerald-500 resize-y"
            />
          </div>

          <div className="mt-3 flex items-center gap-2">
            <Button
              size="sm"
              variant="primary"
              disabled={busy || !notes.trim()}
              onClick={() => onAccept(messageId, card.id, { notes: notes.trim() })}
            >
              {busy ? (
                <span className="flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Saving…
                </span>
              ) : (
                card.action.label || "I've reported it"
              )}
            </Button>
            <span className="text-[11px] text-zinc-400">
              Intake stays paused until you acknowledge.
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
