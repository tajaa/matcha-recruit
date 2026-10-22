import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Bot, Loader2, MessageCircle, RefreshCw, Send, Sparkles } from 'lucide-react'
import { cappeApi } from '../../../api'
import type { CappeSocialInboxItem, CappeSocialInboxStatus, CappeSocialReply, CappeSocialSettings } from '../../../types'

const TABS: { key: string; label: string; statuses: CappeSocialInboxStatus[] }[] = [
  { key: 'needs', label: 'Needs you', statuses: ['new', 'drafted', 'escalated'] },
  { key: 'replied', label: 'Replied', statuses: ['replied'] },
  { key: 'skipped', label: 'Skipped', statuses: ['skipped'] },
]

const WHO: Record<CappeSocialReply['mode'], string> = { auto: 'Auto-reply', approved: 'You approved', manual: 'You' }

function openDraft(item: CappeSocialInboxItem): CappeSocialReply | undefined {
  return [...item.replies].reverse().find((r) => r.status === 'draft')
}

export default function Inbox({ siteId, settings }: { siteId: string; settings: CappeSocialSettings | null }) {
  const [items, setItems] = useState<CappeSocialInboxItem[] | null>(null)
  const [tab, setTab] = useState('needs')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [tick, setTick] = useState(0)
  const generation = useRef(0)

  useEffect(() => {
    const gen = ++generation.current
    cappeApi.get<CappeSocialInboxItem[]>(`/sites/${siteId}/social/inbox?limit=200`)
      .then((list) => { if (gen === generation.current) { setItems(list); setError(null) } })
      .catch((e) => { if (gen === generation.current) setError(e instanceof Error ? e.message : 'Couldn’t load the inbox') })
  }, [siteId, tick])

  const statuses = TABS.find((t) => t.key === tab)?.statuses ?? []
  const shown = (items ?? []).filter((i) => statuses.includes(i.status))
  const canDraft = !!settings?.autoreply_available && settings?.ai_available !== false
  const base = `/sites/${siteId}/social/inbox`

  async function act(item: CappeSocialInboxItem, run: () => Promise<CappeSocialInboxItem>) {
    setBusy(item.id)
    setError(null)
    try {
      const updated = await run()
      setItems((list) => (list ?? []).map((x) => (x.id === item.id ? updated : x)))
      setEdits((e) => { const next = { ...e }; delete next[item.id]; return next })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'That didn’t work')
    } finally {
      setBusy(null)
    }
  }

  const draft = (item: CappeSocialInboxItem) =>
    act(item, () => cappeApi.post<CappeSocialInboxItem>(`${base}/${item.id}/draft`))
  const skip = (item: CappeSocialInboxItem) =>
    act(item, () => cappeApi.post<CappeSocialInboxItem>(`${base}/${item.id}/skip`))
  const send = (item: CappeSocialInboxItem, body: string, replyId?: string) => {
    if (!body.trim()) { setError('Write a reply first'); return }
    void act(item, () => cappeApi.post<CappeSocialInboxItem>(`${base}/${item.id}/reply`, { body: body.trim(), reply_id: replyId ?? null }))
  }

  return (
    <div>
      {settings && settings.autoreply_mode !== 'off' && (
        <p className="mb-3 flex items-center gap-2 text-xs text-zinc-400">
          <Bot className="h-4 w-4 text-lime-400" />
          {settings.autoreply_mode === 'auto'
            ? 'Simple questions get answered automatically; anything else waits here with a draft.'
            : 'New comments and messages get a draft reply here for you to approve.'}
        </p>
      )}
      <div className="mb-4 flex items-center gap-2">
        <div className="flex flex-1 gap-1 rounded-lg border border-zinc-800 bg-zinc-900 p-1">
          {TABS.map((t) => (
            <button key={t.key} type="button" onClick={() => setTab(t.key)}
              className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium ${tab === t.key
                ? 'bg-lime-400 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}>
              {t.label} {items && <span className="opacity-70">{items.filter((i) => t.statuses.includes(i.status)).length}</span>}
            </button>
          ))}
        </div>
        <button type="button" onClick={() => setTick((n) => n + 1)} aria-label="Refresh"
          className="rounded-lg border border-zinc-700 p-2 text-zinc-400 hover:bg-zinc-800"><RefreshCw className="h-4 w-4" /></button>
      </div>
      {error && <p role="alert" className="mb-3 text-sm text-red-400">{error}</p>}
      {items === null && !error ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>
      ) : shown.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 py-12 text-center text-sm text-zinc-500">
          <MessageCircle className="mx-auto mb-2 h-7 w-7 text-zinc-500" />
          {tab === 'needs' ? 'You’re all caught up.' : 'Nothing here yet.'}
        </div>
      ) : (
        <div className="space-y-3">
          {shown.map((item) => {
            const open = openDraft(item)
            const value = edits[item.id] ?? open?.body ?? ''
            const history = item.replies.filter((r) => r.status === 'sent' || r.status === 'failed')
            return (
              <div key={item.id} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
                <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
                  <span className="font-semibold capitalize text-zinc-200">{item.platform}</span>
                  {item.handle && <span>@{item.handle}</span>}
                  <span>· {item.kind === 'message' ? 'Message' : 'Comment'} from {item.author_name || 'someone'}</span>
                  <span>· {new Date(item.received_at).toLocaleString()}</span>
                  {item.status === 'escalated' && (
                    <span className="inline-flex items-center gap-1 rounded bg-amber-500/15 px-1.5 py-0.5 font-semibold text-amber-400">
                      <AlertTriangle className="h-3 w-3" />
                      {item.classification.escalated_on ? `Mentions “${item.classification.escalated_on}”` : 'Needs your eye'}
                    </span>
                  )}
                  {item.classification.intent && item.classification.intent !== 'other' && (
                    <span className="rounded bg-zinc-800 px-1.5 py-0.5">{item.classification.intent.replace(/_/g, ' ')}</span>
                  )}
                </div>
                <p className="mt-2 whitespace-pre-wrap break-words text-sm text-zinc-100">{item.text}</p>

                {history.map((r) => (
                  <div key={r.id} className={`mt-3 border-l-2 pl-3 text-sm ${r.status === 'failed' ? 'border-red-500/60 text-red-300' : 'border-zinc-700 text-zinc-400'}`}>
                    <span className="font-medium text-zinc-300">{WHO[r.mode]}{r.status === 'failed' ? ' (not sent)' : ''}:</span> {r.body}
                    {r.status === 'failed' && r.error && <div className="text-xs">{r.error}</div>}
                  </div>
                ))}

                {item.status !== 'replied' && item.status !== 'skipped' && (
                  <div className="mt-3 space-y-2">
                    {open && (
                      <div className="flex items-center gap-1.5 text-xs text-lime-300">
                        <Sparkles className="h-3.5 w-3.5" /> Suggested reply — edit it or send as is
                      </div>
                    )}
                    <textarea value={value} onChange={(e) => setEdits((ed) => ({ ...ed, [item.id]: e.target.value }))}
                      rows={2} maxLength={2000} aria-label="Your reply" placeholder="Write a reply…"
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-lime-500" />
                    {open?.grounding?.facts_used && open.grounding.facts_used.length > 0 && (
                      <details className="text-xs text-zinc-500">
                        <summary className="cursor-pointer">Based on</summary>
                        <ul className="mt-1 list-disc pl-4">{open.grounding.facts_used.map((f, i) => <li key={i}>{f}</li>)}</ul>
                      </details>
                    )}
                    <div className="flex flex-wrap items-center gap-2">
                      <button type="button" disabled={busy === item.id || !value.trim()}
                        onClick={() => send(item, value, open?.id)}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-lime-400 px-3 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-lime-300 disabled:opacity-50">
                        {busy === item.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />} Send
                      </button>
                      {canDraft && (
                        <button type="button" disabled={busy === item.id} onClick={() => draft(item)}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-lime-300 hover:bg-zinc-800 disabled:opacity-50">
                          <Sparkles className="h-3.5 w-3.5" /> {open ? 'Try another' : 'Draft with AI'}
                        </button>
                      )}
                      <button type="button" disabled={busy === item.id} onClick={() => skip(item)}
                        className="text-xs text-zinc-400 hover:text-zinc-200">Skip</button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
