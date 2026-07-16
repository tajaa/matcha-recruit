import { useState } from 'react'
import { HelpCircle, Loader2, Send, X } from 'lucide-react'
import { authStreamHeaders } from '../../api/client'
import type { PageHelp } from '../../data/pageHelp'

type Message = { role: 'user' | 'assistant'; text: string }

// Floating per-page help widget ("Guide" for the tenant app), mounted once in
// AppLayout and keyed by the current page's help entry. Opens to the authored
// blurb instantly (no AI call); free-form questions stream from the backend
// help assistant (POST /assistant/help), grounded in that same blurb.
// Read-only — it explains, it never takes an action. Streaming loop lifted
// from pages/admin/studio/StudioAssistant.tsx.
export default function HelpAssistant({ pageHelp }: { pageHelp: PageHelp }) {
  const [open, setOpen] = useState(false)
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
      const res = await fetch(`${base}/assistant/help`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          page_context: { title: pageHelp.title, summary: pageHelp.summary, tips: pageHelp.tips },
        }),
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
                next[next.length - 1] = { role: 'assistant', text: ev.message || 'Something went wrong' }
                return next
              })
              setStreaming(false)
            }
          } catch { /* ignore malformed SSE lines */ }
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

  return (
    <>
      {/* z-40, below the z-50 mobile sidebar overlay so an open menu covers it */}
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open page help"
          className="fixed bottom-6 right-6 z-40 flex h-11 w-11 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 text-zinc-300 shadow-lg transition-colors hover:border-emerald-600/60 hover:text-emerald-400"
        >
          <HelpCircle className="h-5 w-5" strokeWidth={1.8} />
        </button>
      )}

      {open && (
        <div className="fixed bottom-6 right-6 z-40 flex max-h-[70vh] w-80 flex-col overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950 shadow-2xl">
          <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2.5">
            <p className="font-mono text-[10px] uppercase tracking-wide text-zinc-400">
              Help · {pageHelp.title}
            </p>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close help" className="text-zinc-600 hover:text-zinc-300">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto px-3 py-3">
            {/* Authored blurb — always shown, zero AI cost */}
            <div className="space-y-2">
              <p className="text-xs leading-relaxed text-zinc-400">{pageHelp.summary}</p>
              <ul className="space-y-1.5">
                {pageHelp.tips.map((tip) => (
                  <li key={tip} className="flex gap-1.5 text-xs leading-relaxed text-zinc-500">
                    <span className="mt-[3px] h-1 w-1 shrink-0 rounded-full bg-emerald-600/70" />
                    <span>{tip}</span>
                  </li>
                ))}
              </ul>
            </div>

            {messages.length === 0 && pageHelp.suggestions && pageHelp.suggestions.length > 0 && (
              <div className="space-y-1.5 border-t border-zinc-800/60 pt-3">
                {pageHelp.suggestions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => ask(s)}
                    className="block w-full rounded-lg border border-zinc-800 bg-zinc-900/60 px-2.5 py-1.5 text-left text-xs text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} className={m.role === 'user' ? 'text-right' : ''}>
                <div
                  className={`inline-block max-w-[95%] rounded-lg px-2.5 py-1.5 text-xs leading-relaxed ${
                    m.role === 'user'
                      ? 'bg-zinc-800 text-zinc-200'
                      : 'border border-emerald-500/10 bg-emerald-500/[0.06] text-zinc-300'
                  }`}
                >
                  {m.text || (streaming && i === messages.length - 1 ? <Loader2 className="inline h-3 w-3 animate-spin" /> : '')}
                </div>
              </div>
            ))}
          </div>

          <form onSubmit={(e) => { e.preventDefault(); ask(input) }} className="border-t border-zinc-800 p-2">
            <div className="flex items-center gap-1.5">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={streaming}
                placeholder="Ask about this page…"
                className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900/60 px-2.5 py-1.5 text-xs text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-600 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={streaming || !input.trim()}
                aria-label="Send question"
                className="rounded-lg border border-zinc-800 p-1.5 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200 disabled:opacity-40"
              >
                <Send className="h-3.5 w-3.5" />
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  )
}
