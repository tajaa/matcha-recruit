import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Send } from 'lucide-react'
import { cappePublicGet, cappePublicPost } from '../../api/cappeClient'
import type { CappePublicThread } from '../../types/cappe'

function when(ts: string) {
  return new Date(ts).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// Public, token-gated conversation page a client reaches from an email link.
export default function ClientThread() {
  const { token } = useParams<{ token: string }>()
  const [thread, setThread] = useState<CappePublicThread | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    cappePublicGet<CappePublicThread>(`/public/threads/${token}`)
      .then(setThread)
      .catch((e) => setError(e instanceof Error ? e.message : 'Conversation not found'))
  }, [token])

  useEffect(() => { bottomRef.current?.scrollIntoView() }, [thread?.messages.length])

  async function send() {
    if (!draft.trim() || !thread) return
    setSending(true)
    const body = draft.trim()
    try {
      await cappePublicPost(`/public/threads/${token}/messages`, { body })
      setThread({
        ...thread,
        messages: [...thread.messages, { id: `tmp-${Date.now()}`, thread_id: '', sender: 'client', body, created_at: new Date().toISOString() }],
      })
      setDraft('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send')
    } finally {
      setSending(false)
    }
  }

  const input = 'w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-lime-500'

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
        <p className="text-sm text-zinc-400">{error}</p>
      </div>
    )
  }
  if (!thread) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
      </div>
    )
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 px-6 py-5">
        <div className="text-xs uppercase tracking-wide text-lime-400">{thread.site_name}</div>
        <h1 className="text-lg font-semibold text-zinc-50">{thread.subject || 'Conversation'}</h1>
      </header>
      <div className="flex-1 space-y-3 overflow-y-auto px-6 py-5">
        {thread.messages.map((m) => (
          <div key={m.id} className={`flex ${m.sender === 'client' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[78%] rounded-2xl px-4 py-2 text-sm ${m.sender === 'client' ? 'bg-lime-400 text-zinc-950' : 'bg-zinc-800 text-zinc-100'}`}>
              <div className="whitespace-pre-wrap break-words">{m.body}</div>
              <div className={`mt-1 text-[10px] ${m.sender === 'client' ? 'text-zinc-800/70' : 'text-zinc-500'}`}>{when(m.created_at)}</div>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="border-t border-zinc-800 p-4">
        <div className="flex items-end gap-2">
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Write a reply…" rows={2} className={input} />
          <button onClick={send} disabled={sending || !draft.trim()} className="flex items-center gap-1.5 rounded-lg bg-lime-400 px-4 py-2.5 text-sm font-semibold text-zinc-950 hover:bg-lime-300 disabled:opacity-60">
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  )
}
