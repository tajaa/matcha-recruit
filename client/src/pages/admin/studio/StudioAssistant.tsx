import { useState } from 'react'
import { Loader2, Send, X } from 'lucide-react'
import { authStreamHeaders } from '../../../api/client'
import type { GotoParams, StudioView, Worklist, WorklistAction } from './types'

type Message = { role: 'user' | 'assistant'; text: string; action?: WorklistAction['kind'] }

const SUGGESTIONS = [
  'What should I do next?',
  'What does "codify" mean?',
  'Why does scoping matter?',
]

// Maps an action kind mentioned in an answer to a place to jump — best-effort,
// keyword match only. The model never performs actions; it only explains and
// points, so this is purely a convenience shortcut on top of its text.
const KIND_TO_VIEW: Record<WorklistAction['kind'], { view: StudioView; params?: GotoParams & { section?: string } }> = {
  review_staged: { view: 'pipeline', params: { section: 'review' } },
  codify_uncodified: { view: 'pipeline', params: { section: 'review' } },
  research_coverage: { view: 'pipeline', params: { section: 'queue' } },
  confirm_authority: { view: 'authority' },
  ack_drift: { view: 'authority' },
  research_baseline: { view: 'library' },
}

// Trim the worklist before sending — counts + a few item titles per action, not
// full payloads (items can run into the hundreds).
function trimWorklist(w: Worklist | null): unknown {
  if (!w) return null
  return {
    meters: w.meters,
    actions: w.actions.map((a) => {
      const base: Record<string, unknown> = { kind: a.kind, priority: a.priority, count: a.count }
      if (a.kind === 'codify_uncodified') base.auto_reconcilable = a.auto_reconcilable
      if (a.kind === 'confirm_authority') base.by_index = a.by_index.slice(0, 5)
      if ('items' in a) base.sample_titles = (a as { items: { title?: string }[] }).items.slice(0, 5).map((it) => it.title)
      if ('groups' in a) base.sample_labels = a.groups.slice(0, 5).map((g) => g.label)
      return base
    }),
  }
}

// Read-only guide over the worklist — explains the two-funnel system and tells
// the admin what needs attention and why. NO tool calls, NO mutations: every
// real action still goes through its own button elsewhere in the studio.
export default function StudioAssistant({
  worklist, onClose, goto,
}: {
  worklist: Worklist | null
  onClose: () => void
  goto: (view: StudioView, params?: GotoParams & { section?: string }) => void
}) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)

  async function ask(question: string) {
    if (!question.trim() || streaming) return
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', text: question }])
    setStreaming(true)
    setMessages((prev) => [...prev, { role: 'assistant', text: '' }])

    const base = import.meta.env.VITE_API_URL || '/api'
    try {
      const headers = await authStreamHeaders()
      const res = await fetch(`${base}/admin/studio/assistant`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, worklist: trimWorklist(worklist) }),
      })
      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) { setStreaming(false); return }
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        for (const line of decoder.decode(value).split('\n')) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6)
          if (data === '[DONE]') { setStreaming(false); return }
          try {
            const ev = JSON.parse(data)
            if (ev.type === 'content' && ev.text) {
              setMessages((prev) => {
                const next = [...prev]
                next[next.length - 1] = { ...next[next.length - 1], text: next[next.length - 1].text + ev.text }
                return next
              })
            } else if (ev.type === 'error') {
              setMessages((prev) => {
                const next = [...prev]
                next[next.length - 1] = { role: 'assistant', text: `Error: ${ev.message}` }
                return next
              })
              setStreaming(false)
            }
          } catch {}
        }
      }
    } catch (e) {
      setMessages((prev) => {
        const next = [...prev]
        next[next.length - 1] = { role: 'assistant', text: e instanceof Error ? e.message : 'Failed to reach the assistant' }
        return next
      })
    } finally {
      setStreaming(false)
    }
  }

  // Best-effort: if the reply clearly names one worklist action kind, offer a
  // jump button. Pure text match on the answer, no model tool-calling.
  const bestGuess = (text: string): WorklistAction['kind'] | undefined => {
    const hits = (worklist?.actions ?? []).filter((a) => text.toLowerCase().includes(a.kind.replace('_', ' ')))
    return hits[0]?.kind
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-3 py-2.5">
        <p className="font-mono text-[10px] uppercase tracking-wide text-zinc-400">Guide</p>
        <button type="button" onClick={onClose} className="text-zinc-600 hover:text-zinc-300">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-xs text-zinc-500">
              Ask about what needs attention, or what a term means. Read-only —
              I explain and point, I never take an action for you.
            </p>
            <div className="space-y-1.5">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" onClick={() => ask(s)}
                  className="block w-full rounded-lg border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5 text-left text-xs text-zinc-400 hover:border-white/20 hover:text-zinc-200">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => {
          const guess = m.role === 'assistant' ? bestGuess(m.text) : undefined
          return (
            <div key={i} className={m.role === 'user' ? 'text-right' : ''}>
              <div className={`inline-block max-w-[95%] rounded-lg px-2.5 py-1.5 text-xs leading-relaxed ${
                m.role === 'user' ? 'bg-white/[0.08] text-zinc-200' : 'bg-emerald-500/[0.06] text-zinc-300 border border-emerald-500/10'
              }`}>
                {m.text || (streaming && i === messages.length - 1 ? <Loader2 className="inline h-3 w-3 animate-spin" /> : '')}
              </div>
              {guess && !streaming && (
                <div className="mt-1">
                  <button type="button"
                    onClick={() => goto(KIND_TO_VIEW[guess].view, KIND_TO_VIEW[guess].params)}
                    className="text-[10px] text-cyan-400 hover:text-cyan-300">
                    Jump there →
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <form onSubmit={(e) => { e.preventDefault(); ask(input) }} className="border-t border-white/[0.06] p-2">
        <div className="flex items-center gap-1.5">
          <input value={input} onChange={(e) => setInput(e.target.value)} disabled={streaming}
            placeholder="Ask the guide…"
            className="flex-1 rounded-lg border border-white/[0.08] bg-white/[0.02] px-2.5 py-1.5 text-xs text-zinc-100 placeholder-zinc-600 outline-none focus:border-white/20 disabled:opacity-50" />
          <button type="submit" disabled={streaming || !input.trim()}
            className="rounded-lg border border-white/[0.08] p-1.5 text-zinc-400 hover:border-white/20 hover:text-zinc-200 disabled:opacity-40">
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </form>
    </div>
  )
}
