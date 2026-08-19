import { useState } from 'react'
import { Loader2, Send } from 'lucide-react'
import { FIELD } from './shared'
import type { ChatIntakeMessage } from '../../../types/ir'

type Props = {
  messages: ChatIntakeMessage[]
  sending: boolean
  chatError: string | null
  onSend: (text: string) => void
  onFinishInForm: () => void
}

export function ChatThread({ messages, sending, chatError, onSend, onFinishInForm }: Props) {
  const [draft, setDraft] = useState('')

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!draft.trim() || sending) return
    onSend(draft)
    setDraft('')
  }

  return (
    <div className="space-y-3">
      <div className="max-h-[42vh] space-y-2.5 overflow-y-auto pr-1">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm leading-relaxed ${
                m.role === 'user'
                  ? 'bg-emerald-500/15 text-zinc-100 border border-emerald-500/25'
                  : 'bg-zinc-800/60 text-zinc-200 border border-white/[0.06]'
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-xl border border-white/[0.06] bg-zinc-800/60 px-3.5 py-2.5 text-sm text-zinc-400">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Thinking…
            </div>
          </div>
        )}
      </div>

      {chatError && <p className="px-0.5 text-[11px] text-amber-400">{chatError}</p>}

      <form onSubmit={submit} className="flex items-center gap-2">
        <input
          autoFocus
          className={FIELD}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type your reply…"
          disabled={sending}
        />
        <button
          type="submit"
          disabled={sending || !draft.trim()}
          className="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-white transition-colors hover:bg-emerald-500 disabled:opacity-40"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>

      <button type="button" onClick={onFinishInForm} className="text-[11px] text-zinc-500 hover:text-zinc-300 underline">
        Finish in the form instead
      </button>
    </div>
  )
}
