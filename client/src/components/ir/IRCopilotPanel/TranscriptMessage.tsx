import { Mail, Sparkles } from 'lucide-react'
import { fmtWhen } from './helpers'
import { type CopilotMessage } from './types'

interface TranscriptMessageProps {
  m: CopilotMessage
}

export function TranscriptMessage({ m }: TranscriptMessageProps) {
  if (m.message_type === 'text') {
    return (
      <div>
        <div className="flex items-baseline gap-3">
          {m.role === 'user' ? (
            <span className="text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-500">You</span>
          ) : (
            <span className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.15em] text-emerald-400/90">
              <Sparkles className="h-3 w-3" /> Copilot
            </span>
          )}
          <span className="font-mono text-[10px] tabular-nums text-zinc-600">{fmtWhen(m.created_at)}</span>
        </div>
        <p className={`mt-1.5 max-w-[65ch] whitespace-pre-wrap text-sm leading-relaxed ${
          m.role === 'user' ? 'text-zinc-300' : 'text-zinc-200'
        }`}>
          {m.content}
        </p>
      </div>
    )
  }
  if (m.message_type === 'event') {
    const md = (m.metadata || {}) as Record<string, unknown>
    const action = typeof md.action === 'string' ? md.action : null
    const fieldLabel = typeof md.field_label === 'string' ? md.field_label : null
    const newValue = md.new_value
    const prevValue = md.previous_value
    const note = typeof md.note === 'string' ? md.note : null
    const fieldUpdateActions = new Set([
      'set_field',
      'close_incident',
      'quick_reply',
      'numeric_input',
      'text_input',
      'osha_emergency_alert',
    ])
    if (action && fieldUpdateActions.has(action) && fieldLabel) {
      const fmt = (v: unknown): string => {
        if (v === null || v === undefined || v === '') return '—'
        if (typeof v === 'string') return v
        return String(v)
      }
      return (
        <div
          className="max-w-[65ch] rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2.5"
        >
          <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.15em] text-emerald-400 mb-1">
            <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M16.704 5.29a1 1 0 010 1.42l-8 8a1 1 0 01-1.42 0l-4-4a1 1 0 011.42-1.42L8 12.585l7.29-7.295a1 1 0 011.414 0z" clipRule="evenodd"/></svg>
            <span>Updated {fieldLabel}</span>
          </div>
          <div className="flex items-center gap-2 text-sm flex-wrap">
            <span className="text-zinc-500 line-through">{fmt(prevValue)}</span>
            <span className="text-zinc-500">→</span>
            <span className="text-emerald-300 font-medium">{fmt(newValue)}</span>
          </div>
          {note && <div className="text-[11px] text-zinc-500 mt-1.5">{note}</div>}
        </div>
      )
    }
    const infoRequestResponses = Array.isArray(md.responses)
      ? (md.responses as { question: string; answer: string }[])
      : null
    if (infoRequestResponses) {
      return (
        <div
          className="max-w-[65ch] rounded-lg border border-sky-500/30 bg-sky-500/5 px-3 py-2.5"
        >
          <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.15em] text-sky-400 mb-1.5">
            <Mail className="w-3.5 h-3.5" />
            <span>{m.content}</span>
          </div>
          <div className="space-y-1.5">
            {infoRequestResponses.map((resp, i) => (
              <div key={i}>
                <div className="text-[11px] text-zinc-500">{resp.question}</div>
                <div className="text-sm text-zinc-200">{resp.answer}</div>
              </div>
            ))}
          </div>
        </div>
      )
    }
    return (
      <div className="text-xs text-zinc-500 italic px-3">
        · {m.content}
      </div>
    )
  }
  // card messages: rendered below as part of currentCards if still active
  return null
}
