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
  reportId, initialThread, isBrand,
}: {
  reportId?: string
  initialThread?: DmThread
  isBrand: boolean
}) {
  const [thread, setThread] = useState<DmThread | null>(initialThread ?? null)
  const [messages, setMessages] = useState<DmMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const comms = initialThread?.kind === 'general'

  async function loadThread() {
    setLoading(true); setErr('')
    try {
      let found = initialThread ?? null
      if (!found) {
        const threads = await tellusApi.get<DmThread[]>(comms ? '/comms/threads' : '/dm/threads')
        found = threads.find((t) => t.report_id === reportId) ?? null
      }
      setThread(found)
      if (found) {
        const msgs = await tellusApi.get<DmMessage[]>(`${comms ? '/comms' : '/dm'}/threads/${found.id}/messages`)
        setMessages(msgs)
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load conversation')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void loadThread() }, [reportId, initialThread?.id])

  useEffect(() => {
    if (!thread || thread.kind !== 'general') return
    let stopped = false
    async function poll() {
      if (stopped || document.visibilityState !== 'visible') return
      const last = messages[messages.length - 1]
      try {
        const delta = await tellusApi.get<DmMessage[]>(`/comms/threads/${thread!.id}/messages${last ? `?after=${last.id}` : ''}`)
        if (delta.length) setMessages((cur) => {
          const seen = new Set(cur.map(m => m.id)); return [...cur, ...delta.filter(m => !seen.has(m.id))]
        })
      } catch { /* transient poll failures are silent */ }
    }
    const id = window.setInterval(() => void poll(), 5000)
    return () => { stopped = true; window.clearInterval(id) }
  }, [thread?.id, thread?.kind, messages.length])

  async function send() {
    if (!body.trim()) return
    setBusy(true); setErr('')
    try {
      if (!thread && reportId) {
        // Brand's first message opens the thread.
        const opened = await tellusApi.post<DmThread>(`/feedback/${reportId}/dm`, { body })
        setThread(opened)
        setBody('')
        const msgs = await tellusApi.get<DmMessage[]>(`/dm/threads/${opened.id}/messages`)
        setMessages(msgs)
      } else if (thread) {
        const msg = await tellusApi.post<DmMessage>(`${thread.kind === 'general' ? '/comms' : '/dm'}/threads/${thread.id}/messages`, { body, client_message_id: crypto.randomUUID() })
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
      if (thread.kind === 'general') {
        if (thread.blocked) await tellusApi.delete(`/comms/threads/${thread.id}/block`)
        else await tellusApi.post(`/comms/threads/${thread.id}/block`)
      } else if (thread.blocked) await tellusApi.delete(`/dm/threads/${thread.id}/block`)
      else await tellusApi.post(`/dm/threads/${thread.id}/block`)
      setThread({ ...thread, blocked: !thread.blocked })
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  async function takeThread() {
    if (!thread || thread.kind !== 'general') return
    setBusy(true); setErr('')
    try { setThread(await tellusApi.post<DmThread>(`/comms/threads/${thread.id}/take`)) }
    catch (e) { setErr(e instanceof Error ? e.message : 'Could not take conversation') }
    finally { setBusy(false) }
  }

  async function closeThread() {
    if (!thread || thread.kind !== 'general') return
    setBusy(true); setErr('')
    try { setThread(await tellusApi.post<DmThread>(`/comms/threads/${thread.id}/close`)) }
    catch (e) { setErr(e instanceof Error ? e.message : 'Could not close conversation') }
    finally { setBusy(false) }
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
  const canCompose = isBrand ? !blocked && thread?.status !== 'closed' : !!thread && !blocked && thread.status !== 'closed'

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

      {isBrand && thread?.kind === 'general' && (
        <div className="mb-2 flex items-center gap-2 text-xs text-tu-faint">
          {!thread.assigned_member_id && <Button size="sm" variant="soft" loading={busy} onClick={() => void takeThread()}>Take</Button>}
          {thread.status !== 'closed' && <Button size="sm" variant="ghost" loading={busy} onClick={() => void closeThread()}>Close</Button>}
        </div>
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
