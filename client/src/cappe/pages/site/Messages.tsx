import { useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { Loader2, Send, Plus, MessageSquare, X } from 'lucide-react'
import { cappeApi } from '../../api'
import type { CappeThread, CappeThreadDetail } from '../../types'

function when(ts: string) {
  return new Date(ts).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function Messages() {
  const { siteId } = useParams<{ siteId: string }>()
  const [params, setParams] = useSearchParams()
  const [threads, setThreads] = useState<CappeThread[] | null>(null)
  const [active, setActive] = useState<CappeThreadDetail | null>(null)
  const [loadingThread, setLoadingThread] = useState(false)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [composing, setComposing] = useState(false)
  const [newThread, setNewThread] = useState({ client_email: '', client_name: '', subject: '', body: '' })
  const bottomRef = useRef<HTMLDivElement>(null)

  // Deep-link: ?to=email&name= prefills a new conversation (from Clients).
  const presetTo = params.get('to')

  useEffect(() => {
    cappeApi.get<CappeThread[]>(`/sites/${siteId}/threads`)
      .then(setThreads)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
  }, [siteId])

  useEffect(() => {
    if (presetTo) {
      setComposing(true)
      setNewThread((n) => ({ ...n, client_email: presetTo, client_name: params.get('name') || '' }))
    }
  }, [presetTo]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { bottomRef.current?.scrollIntoView() }, [active?.messages.length])

  async function openThread(t: CappeThread) {
    setComposing(false)
    setLoadingThread(true)
    try {
      const full = await cappeApi.get<CappeThreadDetail>(`/sites/${siteId}/threads/${t.id}`)
      setActive(full)
      setThreads((list) => (list || []).map((x) => (x.id === t.id ? { ...x, owner_unread: 0 } : x)))
    } finally {
      setLoadingThread(false)
    }
  }

  async function send() {
    if (!active || !draft.trim()) return
    setSending(true)
    try {
      const msg = await cappeApi.post<CappeThreadDetail['messages'][number]>(
        `/sites/${siteId}/threads/${active.id}/messages`, { body: draft.trim() },
      )
      setActive({ ...active, messages: [...active.messages, msg] })
      setDraft('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send')
    } finally {
      setSending(false)
    }
  }

  async function startThread() {
    if (!newThread.client_email.trim() || !newThread.body.trim()) return
    setSending(true)
    setError(null)
    try {
      const created = await cappeApi.post<CappeThreadDetail>(`/sites/${siteId}/threads`, {
        client_email: newThread.client_email.trim(),
        client_name: newThread.client_name.trim() || null,
        subject: newThread.subject.trim() || null,
        body: newThread.body.trim(),
      })
      setThreads((list) => {
        const others = (list || []).filter((t) => t.id !== created.id)
        return [created, ...others]
      })
      setActive(created)
      setComposing(false)
      setNewThread({ client_email: '', client_name: '', subject: '', body: '' })
      if (presetTo) setParams({})
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start conversation')
    } finally {
      setSending(false)
    }
  }

  const input = 'w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-lime-500'

  return (
    <div className="flex h-screen">
      {/* Thread list */}
      <div className="flex w-80 shrink-0 flex-col border-r border-zinc-800">
        <div className="flex items-center justify-between px-4 py-4">
          <h1 className="text-lg font-semibold text-zinc-50">Messages</h1>
          <button onClick={() => { setComposing(true); setActive(null) }} className="flex items-center gap-1 rounded-lg bg-lime-400 px-2.5 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-lime-300">
            <Plus className="h-3.5 w-3.5" /> New
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {threads === null ? (
            <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-zinc-500" /></div>
          ) : threads.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-zinc-500">No conversations yet.</p>
          ) : (
            threads.map((t) => (
              <button
                key={t.id}
                onClick={() => openThread(t)}
                className={`flex w-full flex-col gap-0.5 border-b border-zinc-800/70 px-4 py-3 text-left hover:bg-zinc-800/40 ${active?.id === t.id ? 'bg-zinc-800/60' : ''}`}
              >
                <div className="flex items-center justify-between">
                  <span className="truncate text-sm font-medium text-zinc-200">{t.client_name || t.client_email}</span>
                  {t.owner_unread > 0 && <span className="ml-2 rounded-full bg-lime-400 px-1.5 text-[10px] font-bold text-zinc-950">{t.owner_unread}</span>}
                </div>
                {t.subject && <span className="truncate text-xs text-zinc-400">{t.subject}</span>}
                <span className="truncate text-xs text-zinc-500">{t.last_snippet || ''}</span>
                <span className="text-[11px] text-zinc-600">{when(t.last_message_at)}</span>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Conversation / composer */}
      <div className="flex flex-1 flex-col">
        {error && <p className="px-6 pt-4 text-sm text-red-400">{error}</p>}

        {composing ? (
          <div className="mx-auto w-full max-w-lg px-6 py-8">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-base font-semibold text-zinc-100">New conversation</h2>
              <button onClick={() => setComposing(false)} className="text-zinc-500 hover:text-zinc-300"><X className="h-4 w-4" /></button>
            </div>
            <div className="space-y-3">
              <input value={newThread.client_email} onChange={(e) => setNewThread({ ...newThread, client_email: e.target.value })} placeholder="Client email" type="email" className={input} />
              <input value={newThread.client_name} onChange={(e) => setNewThread({ ...newThread, client_name: e.target.value })} placeholder="Client name (optional)" className={input} />
              <input value={newThread.subject} onChange={(e) => setNewThread({ ...newThread, subject: e.target.value })} placeholder="Subject (optional)" className={input} />
              <textarea value={newThread.body} onChange={(e) => setNewThread({ ...newThread, body: e.target.value })} placeholder="Your message…" rows={5} className={input} />
              <button onClick={startThread} disabled={sending || !newThread.client_email.trim() || !newThread.body.trim()} className="flex items-center gap-1.5 rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-300 disabled:opacity-60">
                {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Send
              </button>
            </div>
          </div>
        ) : !active ? (
          <div className="flex flex-1 flex-col items-center justify-center text-zinc-600">
            <MessageSquare className="h-8 w-8" />
            <p className="mt-2 text-sm">{loadingThread ? 'Loading…' : 'Select a conversation'}</p>
          </div>
        ) : (
          <>
            <div className="border-b border-zinc-800 px-6 py-4">
              <div className="text-sm font-semibold text-zinc-100">{active.client_name || active.client_email}</div>
              {active.subject && <div className="text-xs text-zinc-400">{active.subject}</div>}
            </div>
            <div className="flex-1 space-y-3 overflow-y-auto px-6 py-5">
              {active.messages.map((m) => (
                <div key={m.id} className={`flex ${m.sender === 'owner' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm ${m.sender === 'owner' ? 'bg-lime-400 text-zinc-950' : 'bg-zinc-800 text-zinc-100'}`}>
                    <div className="whitespace-pre-wrap break-words">{m.body}</div>
                    <div className={`mt-1 text-[10px] ${m.sender === 'owner' ? 'text-zinc-800/70' : 'text-zinc-500'}`}>{when(m.created_at)}</div>
                  </div>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
            <div className="border-t border-zinc-800 p-4">
              <div className="flex items-end gap-2">
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send() }}
                  placeholder="Write a reply…  (⌘↵ to send)"
                  rows={2}
                  className={input}
                />
                <button onClick={send} disabled={sending || !draft.trim()} className="flex items-center gap-1.5 rounded-lg bg-lime-400 px-4 py-2.5 text-sm font-semibold text-zinc-950 hover:bg-lime-300 disabled:opacity-60">
                  {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
