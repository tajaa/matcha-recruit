// The design assistant rail — chat plus generated whole-flyer ideas.
//
// Swaps with the inspector rather than sitting beside it: the designer already
// has two rails, and a third would leave the artboard too narrow to work on.
import { useEffect, useRef, useState } from 'react'
import { Check, Send, Sparkles, X } from 'lucide-react'
import type { FlyerIdea } from '../../api/types'
import type { AssistantMessage } from '../../hooks/useFlyerAssistant'
import { Button, ErrorText, Spinner } from '../ui'
import { TemplatePreview } from './TemplatePreview'

const IDEA_PREVIEW_W = 120

// Openers that map onto what the assistant is actually good at — a palette
// swap, a whole layout, one targeted fix — rather than inviting freeform
// requests it will have to refuse.
const QUICK_PROMPTS = [
  'Make it feel warmer',
  'Make the headline bigger',
  'Give it a dark, high-contrast look',
  'Move the QR to the bottom right',
]

export interface AssistantPanelProps {
  messages: AssistantMessage[]
  sending: boolean
  error: string
  onSend: (text: string) => void
  ideas: FlyerIdea[]
  ideasLoading: boolean
  onLoadIdeas: () => void
  onApplyIdea: (idea: FlyerIdea) => void
  onClose: () => void
  stickerSrc: (assetId: string) => string
  selectedLabel: string | null
}

export function AssistantPanel({
  messages, sending, error, onSend, ideas, ideasLoading, onLoadIdeas, onApplyIdea,
  onClose, stickerSrc, selectedLabel,
}: AssistantPanelProps) {
  const [draft, setDraft] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, sending])

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!draft.trim() || sending) return
    onSend(draft)
    setDraft('')
  }

  return (
    <div className="flex h-full w-80 shrink-0 flex-col border-l border-tu-border bg-tu-panel">
      <div className="flex items-center gap-2 border-b border-tu-border px-3 py-2">
        <Sparkles className="h-4 w-4 text-tu-accent" />
        <span className="text-sm font-semibold">Design assistant</span>
        <button onClick={onClose} className="ml-auto text-tu-faint hover:text-tu-text" title="Close">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        {messages.length === 0 && (
          <div className="space-y-3">
            <p className="text-xs text-tu-faint">
              Ask for a change in plain language, or start from a generated idea. Every change is a
              single undo away.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {QUICK_PROMPTS.map((p) => (
                <button
                  key={p}
                  onClick={() => onSend(p)}
                  disabled={sending}
                  className="rounded-full border border-tu-border px-2.5 py-1 text-xs text-tu-dim transition hover:border-tu-accent hover:text-tu-text disabled:opacity-50"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} className={m.role === 'user' ? 'text-right' : ''}>
            <div
              className={`inline-block max-w-[92%] rounded-lg px-2.5 py-1.5 text-left text-xs ${
                m.role === 'user' ? 'bg-tu-accent/15 text-tu-text' : 'bg-tu-panel2 text-tu-dim'
              }`}
            >
              {m.content}
            </div>
            {/* Per-op chips. The server applied these, so they are what actually
                happened — not a restatement of what was asked for. */}
            {m.results?.length ? (
              <ul className="mt-1 space-y-0.5">
                {m.results.map((r, i) => (
                  <li key={i} className={`flex items-start gap-1 text-xs ${r.ok ? 'text-tu-faint' : 'text-tu-bad'}`}>
                    <Check className={`mt-0.5 h-3 w-3 shrink-0 ${r.ok ? '' : 'opacity-0'}`} />
                    <span>{r.summary}</span>
                  </li>
                ))}
              </ul>
            ) : null}
            {m.rejected?.length ? (
              <ul className="mt-1 space-y-0.5">
                {m.rejected.map((r, i) => (
                  <li key={i} className="text-xs text-tu-faint">Skipped — {r.reason}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ))}

        {sending && <Spinner />}
        <ErrorText>{error}</ErrorText>
        <div ref={endRef} />
      </div>

      <div className="shrink-0 border-t border-tu-border p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-tu-dim">Ideas</span>
          <Button size="sm" variant="soft" loading={ideasLoading} onClick={onLoadIdeas} disabled={sending}>
            <Sparkles className="h-3.5 w-3.5" /> {ideas.length ? 'Regenerate' : 'Generate'}
          </Button>
        </div>
        {ideas.length > 0 && (
          <div className="mb-3 grid grid-cols-3 gap-2">
            {ideas.map((idea) => (
              <button
                key={idea.key}
                onClick={() => onApplyIdea(idea)}
                title={idea.blurb}
                disabled={sending}
                className="overflow-hidden rounded-md border border-tu-border transition hover:border-tu-accent disabled:opacity-50"
              >
                <TemplatePreview design={idea.design} width={IDEA_PREVIEW_W} stickerSrc={stickerSrc} />
              </button>
            ))}
          </div>
        )}

        <form onSubmit={submit} className="flex items-end gap-2">
          <textarea
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(e) }
            }}
            placeholder={selectedLabel ? `Change ${selectedLabel}…` : 'Ask for a change…'}
            className="min-h-0 flex-1 resize-none rounded-lg border border-tu-border bg-tu-panel2 px-2.5 py-1.5 text-xs text-tu-text placeholder:text-tu-faint focus:border-tu-accent focus:outline-none"
          />
          <Button size="sm" type="submit" loading={sending} disabled={!draft.trim()}>
            <Send className="h-3.5 w-3.5" />
          </Button>
        </form>
        {selectedLabel && (
          <p className="mt-1 text-xs text-tu-faint">
            "this" refers to {selectedLabel}.
          </p>
        )}
      </div>
    </div>
  )
}
