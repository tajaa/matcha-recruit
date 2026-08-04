import { useEffect, useState } from 'react'
import { Send, ShieldOff } from 'lucide-react'
import { tellusApi } from '../api/tellusClient'
import { Button, Spinner } from './ui'
import type { DmMessage, DmThread } from '../api/types'

// Shared brand+consumer DM widget — a brand opens the one thread for a
// report (POST /feedback/{id}/dm, first message included); after that both
// sides just send into the existing thread. Rendered inline under a report
// row / review card, not as its own page — no modal/drawer primitive exists
// in this app, so this follows the established inline-expansion pattern.
export function DmThreadPanel({
  reportId, isBrand,
}: {
  reportId: string
  isBrand: boolean
}) {
  const [thread, setThread] = useState<DmThread | null>(null)
  const [messages, setMessages] = useState<DmMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function loadThread() {
    setLoading(true); setErr('')
    try {
      const threads = await tellusApi.get<DmThread[]>('/dm/threads')
      const found = threads.find((t) => t.report_id === reportId) ?? null
      setThread(found)
      if (found) {
        const msgs = await tellusApi.get<DmMessage[]>(`/dm/threads/${found.id}/messages`)
        setMessages(msgs)
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load conversation')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadThread() }, [reportId])

  async function send() {
    if (!body.trim()) return
    setBusy(true); setErr('')
    try {
      if (!thread) {
        // Brand's first message opens the thread.
        const opened = await tellusApi.post<DmThread>(`/feedback/${reportId}/dm`, { body })
        setThread(opened)
        setBody('')
        const msgs = await tellusApi.get<DmMessage[]>(`/dm/threads/${opened.id}/messages`)
        setMessages(msgs)
      } else {
        const msg = await tellusApi.post<DmMessage>(`/dm/threads/${thread.id}/messages`, { body })
        setMessages((m) => [...m, msg])
        setBody('')
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Message failed to send')
    } finally {
      setBusy(false)
    }
  }

  async function toggleBlock() {
    if (!thread) return
    setBusy(true); setErr('')
    try {
      if (thread.blocked) await tellusApi.delete(`/dm/threads/${thread.id}/block`)
      else await tellusApi.post(`/dm/threads/${thread.id}/block`)
      setThread({ ...thread, blocked: !thread.blocked })
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <div className="py-4"><Spinner /></div>
  if (err && !thread && messages.length === 0) {
    return (
      <div className="rounded-lg border border-tu-border bg-tu-panel2 p-3">
        <p className="text-xs text-tu-bad">{err}</p>
        <Button size="sm" variant="ghost" className="mt-2" onClick={() => void loadThread()}>Retry</Button>
      </div>
    )
  }

  const blocked = thread?.blocked ?? false
  const canCompose = isBrand ? !blocked : !!thread && !blocked

  return (
    <div className="rounded-lg border border-tu-border bg-tu-panel2 p-3">
      {messages.length === 0 && (
        <p className="text-xs text-tu-faint">
          {isBrand ? 'Send a message to start the conversation.' : 'No messages yet.'}
        </p>
      )}
      {messages.length > 0 && (
        <div className="mb-2 max-h-64 space-y-1.5 overflow-y-auto">
          {messages.map((m) => (
            <div key={m.id} className={`flex ${m.is_mine ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] rounded-lg px-2.5 py-1.5 text-sm ${
                m.is_mine ? 'bg-tu-accent/15 text-tu-text' : 'bg-tu-panel text-tu-dim'
              }`}>
                {m.body}
              </div>
            </div>
          ))}
        </div>
      )}

      {blocked && !isBrand && (
        <div className="mb-2 flex items-center justify-between rounded-md bg-tu-bad/10 px-2.5 py-1.5 text-xs text-tu-bad">
          <span>You've ended this conversation.</span>
          <Button size="sm" variant="ghost" loading={busy} onClick={toggleBlock}>Unblock</Button>
        </div>
      )}
      {blocked && isBrand && (
        <p className="mb-2 text-xs text-tu-bad">This reviewer has ended the conversation.</p>
      )}

      {canCompose && (
        <div className="flex items-end gap-2">
          <textarea
            value={body} onChange={(e) => setBody(e.target.value)} rows={2}
            placeholder="Write a message…"
            className="flex-1 rounded-lg border border-tu-border bg-tu-panel px-2.5 py-1.5 text-sm text-tu-text placeholder:text-tu-faint focus:border-tu-accent focus:outline-none"
          />
          <Button size="sm" loading={busy} onClick={send}><Send className="h-3.5 w-3.5" /></Button>
        </div>
      )}
      {err && <p className="mt-1 text-xs text-tu-bad">{err}</p>}

      {!isBrand && thread && !blocked && (
        <button onClick={toggleBlock} className="mt-2 flex items-center gap-1 text-xs text-tu-faint hover:text-tu-bad">
          <ShieldOff className="h-3 w-3" /> End conversation
        </button>
      )}
    </div>
  )
}
