import { useEffect, useState } from 'react'
import { Loader2, Send } from 'lucide-react'
import { streamChat, type PilotSession, type PilotMessage } from '../../../api/handbook-pilot/handbookPilot'
import { usePilotChat } from '../../../components/pilot/usePilotChat'
import type { ComposerSeed } from './shared'

const HANDBOOK_EXAMPLES = [
  'Draft a remote-work policy for our California and Texas locations.',
  'Expand our meal-and-rest-break section to cover our Illinois warehouse.',
  'Add a bereavement leave policy consistent with our other leave sections.',
  'Update our anti-harassment policy to reflect this year\'s law changes.',
  'Draft a standalone pay-transparency policy for our open roles.',
]

// --------------------------------------------------------------------------- //
// Console — transcript + composer with SSE streaming.
// --------------------------------------------------------------------------- //

// NB: this component is keyed by session.id in the parent, so it remounts on a
// session switch — `session` is effectively fixed for an instance's lifetime.
export function Console({ session, onTurn, seed, onSeedConsumed, autoSeed }: {
  session: PilotSession
  onTurn: () => void
  seed: ComposerSeed | null
  onSeedConsumed: () => void
  autoSeed: boolean
}) {
  const {
    messages, setMessages, input, setInput, busy, status, setStatus,
    scrollRef, textareaRef, runTurn,
  } = usePilotChat<PilotMessage>({ initialMessages: session.messages ?? [], statusLabel: 'Thinking…', onTurn })
  const [view, setView] = useState<'chat' | 'examples'>('chat')

  // A requirement's Draft button seeds the composer. Consumed on apply, so
  // remounting (mode toggle) never refills an already-sent prompt. Appends
  // rather than replaces — the Requirements rail sits beside a live composer,
  // and clicking Draft must not silently eat a half-typed message.
  useEffect(() => {
    if (!seed) return
    setInput((cur) => (cur.trim() ? `${cur.trimEnd()}\n\n${seed.text}` : seed.text))
    setView('chat')
    textareaRef.current?.focus()
    onSeedConsumed()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed?.nonce])

  const send = async (override?: string) => {
    const text = (override ?? input).trim()
    if (!text || busy) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: text, metadata: null, created_at: new Date().toISOString() }])
    await runTurn(async (signal, markError) => {
      await streamChat(session.id, text, {
        onStatus: (msg) => setStatus(msg),
        onResult: (data) => {
          setMessages((m) => [...m, {
            role: 'assistant', content: data.assistant_text,
            metadata: { open_questions: data.open_questions, dropped_citations: data.dropped_citations },
            created_at: new Date().toISOString(),
          }])
        },
        onError: (msg) => { markError(); setStatus(`⚠ ${msg}`) },
      }, signal)
    })
  }

  // The goal from the New-session modal is the first thing the user typed — it
  // becomes the opening turn rather than sitting inert as a subtitle. Deferred
  // a tick with cleanup: StrictMode's dev mount→cleanup→mount would otherwise
  // let the unmount-abort effect above kill this stream mid-flight, leaving a
  // ghost user message and a stuck composer (aborted turns skip setBusy(false)).
  useEffect(() => {
    if (!autoSeed || messages.length > 0) return
    const goal = session.goal?.trim()
    if (!goal) return
    const t = setTimeout(() => { void send(goal) }, 0)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id])

  return (
    <>
      <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-zinc-100 truncate">{session.title}</div>
          {session.goal && <div className="text-xs text-zinc-500 mt-0.5">{session.goal}</div>}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {(['chat', 'examples'] as const).map((v) => (
            <button key={v} onClick={() => setView(v)}
              className={`px-2 py-1 text-[11px] rounded-md capitalize ${
                view === v ? 'bg-zinc-800 text-emerald-400' : 'text-zinc-500 hover:text-zinc-300'}`}>
              {v === 'chat' ? 'Chat' : 'Examples'}
            </button>
          ))}
        </div>
      </div>
      {view === 'examples' ? (
        <div className="flex-1 overflow-y-auto p-4">
          <p className="text-sm text-zinc-500 mb-3">Click one to drop it into the composer, then edit or send it as-is.</p>
          <div className="space-y-1.5">
            {HANDBOOK_EXAMPLES.map((ex) => (
              <button key={ex}
                onClick={() => { setInput(ex); setView('chat'); textareaRef.current?.focus() }}
                className="block w-full text-left text-[13px] text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/60 rounded-lg px-3 py-2 transition-colors"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>
      ) : (
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-sm text-zinc-600">
            Ask the pilot to draft or revise a handbook section or policy. Every enforceable clause is grounded in
            your applicable jurisdiction requirements — citations that can't be traced are dropped.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
            <div className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm whitespace-pre-wrap ${
              m.role === 'user' ? 'bg-emerald-600 text-white' : 'bg-zinc-800/70 text-zinc-200'
            }`}>
              {m.content}
              {m.role === 'assistant' && m.metadata?.open_questions && m.metadata.open_questions.length > 0 && (
                <div className="mt-2 pt-2 border-t border-zinc-700/60">
                  <div className="text-[11px] uppercase tracking-wide text-amber-400/80 mb-1">Open questions</div>
                  <ul className="list-disc list-inside text-xs text-zinc-400 space-y-0.5">
                    {m.metadata.open_questions.map((q, j) => <li key={j}>{q}</li>)}
                  </ul>
                </div>
              )}
            </div>
          </div>
        ))}
        {status && (
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> {status}
          </div>
        )}
      </div>
      )}
      <div className="p-3 border-t border-zinc-800">
        <div className="flex gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }}
            placeholder="Draft a remote-work policy for our CA and TX locations…"
            rows={2}
            className="flex-1 resize-none rounded-lg bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-emerald-500"
          />
          <button
            onClick={() => void send()}
            disabled={busy || !input.trim()}
            className="px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white self-stretch flex items-center"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </>
  )
}
