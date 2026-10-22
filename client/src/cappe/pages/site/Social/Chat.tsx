import { useEffect, useRef, useState } from 'react'
import { Film, Loader2, MessageSquarePlus, MessagesSquare, Paperclip, Send, Sparkles, X } from 'lucide-react'
import { cappeApi } from '../../../api'
import type {
  CappeSocialChat, CappeSocialChatAttachment, CappeSocialChatMessage, CappeSocialChatSummary, CappeSocialChatTurn,
  CappeSocialConnection, CappeSocialPlanCard, CappeSocialSettings, CappeSocialUpload,
} from '../../../types'
import { posterOf, uploadVideo, VIDEO_TYPES, videoProblem } from '../../../utils/socialVideo'
import ChatList from './ChatList'
import PlanCard from './PlanCard'

// Something dropped into the chat, on its way to the server. A photo is
// ready once it has its `url`, a video once the server has it (`assetId`) —
// it may still be being cut to size, which the plan doesn't need to wait for.
type Drop = {
  key: string
  name: string
  kind: 'image' | 'video'
  preview: string
  url: string | null
  assetId: string | null
  poster: string | null
  uploading: boolean
  progress: number | null
  error: string | null
}

const IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp,image/gif'
const MAX_DROPS = 10
const EXAMPLES = [
  'Post these everywhere tomorrow at 2pm',
  'Prepare this video for all platforms with word-for-word captions',
  'One a day for the next week, starting Monday morning',
  'Link the product and keep it playful',
]
let dropSeq = 0

const storageKey = (siteId: string) => `cappe-social-chat:${siteId}`

function readSaved(siteId: string): string | null {
  try { return localStorage.getItem(storageKey(siteId)) } catch { return null }
}

function save(siteId: string, id: string | null) {
  try {
    if (id) localStorage.setItem(storageKey(siteId), id)
    else localStorage.removeItem(storageKey(siteId))
  } catch { /* private window: the chat just won't come back after a reload */ }
}

/** The chat composer: drop photos and videos, say what to post, where and
 *  when; Claude plans it and writes each network's copy, and nothing goes
 *  out until the plan card is confirmed. A video can also be prepared as
 *  files to download for Instagram, TikTok and YouTube ("prepare this for
 *  all platforms"). Past chats are listed alongside. Server side:
 *  routes/social_chat.py. */
export default function Chat({ siteId, connections, settings, onPosted }: {
  siteId: string
  connections: CappeSocialConnection[]
  settings: CappeSocialSettings | null
  onPosted: (message: string, where?: 'queue' | 'exports') => void
}) {
  const [conversationId, setConversationId] = useState<string | null>(() => readSaved(siteId))
  const [messages, setMessages] = useState<CappeSocialChatMessage[]>([])
  const [card, setCard] = useState<CappeSocialPlanCard | null>(null)
  const [drops, setDrops] = useState<Drop[]>([])
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(() => !!readSaved(siteId))
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [chats, setChats] = useState<CappeSocialChatSummary[] | null>(null)
  const [showChats, setShowChats] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const opening = useRef(0)
  const previews = useRef<Set<string>>(new Set())
  const end = useRef<HTMLDivElement>(null)
  const videoOk = !!settings?.video_available
  const aiReady = settings?.ai_available !== false

  function loadChats() {
    cappeApi.get<CappeSocialChatSummary[]>(`/sites/${siteId}/social/chat/conversations`)
      .then((list) => setChats(Array.isArray(list) ? list : []))
      .catch(() => setChats((c) => c ?? []))
  }

  async function open(id: string) {
    const ticket = ++opening.current
    setLoading(true)
    setError(null)
    setShowChats(false)
    try {
      const chat = await cappeApi.get<CappeSocialChat>(`/sites/${siteId}/social/chat/conversations/${id}`)
      if (ticket !== opening.current) return
      setConversationId(id)
      save(siteId, id)
      setMessages(chat.messages)
      setCard(chat.plan)
    } catch {
      if (ticket !== opening.current) return
      if (readSaved(siteId) === id) save(siteId, null)
      setChats((list) => list?.filter((c) => c.id !== id) ?? list)
      setError('That chat is gone')
    } finally {
      if (ticket === opening.current) setLoading(false)
    }
  }

  useEffect(() => {
    let live = true
    const saved = readSaved(siteId)
    if (saved) {
      cappeApi.get<CappeSocialChat>(`/sites/${siteId}/social/chat/conversations/${saved}`)
        .then((chat) => { if (live) { setMessages(chat.messages); setCard(chat.plan) } })
        .catch(() => { if (live) { save(siteId, null); setConversationId(null) } })
        .finally(() => { if (live) setLoading(false) })
    }
    cappeApi.get<CappeSocialChatSummary[]>(`/sites/${siteId}/social/chat/conversations`)
      .then((list) => { if (live) setChats(Array.isArray(list) ? list : []) })
      .catch(() => { if (live) setChats([]) })
    return () => { live = false }
  }, [siteId])

  async function rename(id: string, title: string) {
    setChats((list) => list?.map((c) => (c.id === id ? { ...c, title } : c)) ?? list)
    try {
      await cappeApi.patch(`/sites/${siteId}/social/chat/conversations/${id}`, { title })
    } catch {
      loadChats()
    }
  }

  async function forget(id: string) {
    try {
      await cappeApi.delete(`/sites/${siteId}/social/chat/conversations/${id}`)
      setChats((list) => list?.filter((c) => c.id !== id) ?? list)
      if (id === conversationId) newChat()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t delete that chat')
    }
  }

  useEffect(() => {
    const urls = previews.current
    return () => urls.forEach((u) => URL.revokeObjectURL(u))
  }, [])

  useEffect(() => { end.current?.scrollIntoView?.({ block: 'end' }) }, [messages, card])

  function update(key: string, patch: Partial<Drop>) {
    setDrops((ds) => ds.map((d) => (d.key === key ? { ...d, ...patch } : d)))
  }

  async function addFiles(files: FileList | File[]) {
    setError(null)
    const all = Array.from(files).filter((f) => f.type.startsWith('image/') || f.type.startsWith('video/'))
    if (all.some((f) => f.type.startsWith('video/')) && !videoOk) {
      setError('Video posts are part of the Business, Pro and Creator plans.')
    }
    const usable = all.filter((f) => f.type.startsWith('image/') || videoOk).slice(0, Math.max(0, MAX_DROPS - drops.length))
    const added = usable.map((file) => {
      const preview = URL.createObjectURL(file)
      previews.current.add(preview)
      const drop: Drop = { key: `d${++dropSeq}`, name: file.name, kind: file.type.startsWith('video/') ? 'video' : 'image',
        preview, url: null, assetId: null, poster: null, uploading: true, progress: null, error: null }
      return { file, drop }
    })
    setDrops((ds) => [...ds, ...added.map((a) => a.drop)])
    await Promise.all(added.map(async ({ file, drop }) => {
      try {
        if (drop.kind === 'video') {
          const problem = videoProblem(file)
          if (problem) throw new Error(problem)
          const asset = await uploadVideo(siteId, file, (progress) => update(drop.key, { progress }))
          if (asset.status === 'failed') throw new Error(asset.error ?? 'We couldn’t prepare that video')
          update(drop.key, { assetId: asset.id, poster: posterOf(asset), uploading: false })
        } else {
          const fd = new FormData()
          fd.append('file', file)
          const res = await cappeApi.upload<CappeSocialUpload>(`/sites/${siteId}/social/media`, fd)
          update(drop.key, { url: res.url, uploading: false })
        }
      } catch (e) {
        update(drop.key, { uploading: false, error: e instanceof Error ? e.message : 'Upload failed' })
      }
    }))
  }

  function remove(key: string) {
    const gone = drops.find((d) => d.key === key)
    if (gone) {
      URL.revokeObjectURL(gone.preview)
      previews.current.delete(gone.preview)
      if (gone.assetId) void cappeApi.delete(`/sites/${siteId}/social/assets/${gone.assetId}`).catch(() => {})
    }
    setDrops((ds) => ds.filter((d) => d.key !== key))
  }

  function newChat() {
    opening.current++
    save(siteId, null)
    setConversationId(null)
    setMessages([])
    setCard(null)
    setError(null)
    setLoading(false)
    setShowChats(false)
  }

  async function send() {
    if (sending) return  // Enter while a turn is in flight would start a second one
    const message = text.trim()
    const ready = drops.filter((d) => !d.error && (d.url || d.assetId))
    if (drops.some((d) => d.uploading)) { setError('Wait for the uploads to finish'); return }
    if (!message && !ready.length) { setError('Drop a photo or a video, or say what to post'); return }
    const attachments: CappeSocialChatAttachment[] = ready.map((d) => (d.kind === 'video'
      ? { kind: 'video', asset_id: d.assetId, name: d.name } : { kind: 'image', url: d.url, name: d.name }))
    const mine: CappeSocialChatMessage = { id: `local-${Date.now()}`, role: 'user', content: message, attachments,
      created_at: new Date().toISOString() }
    const keptDrops = drops
    setMessages((m) => [...m, mine])
    setText('')
    setDrops([])
    setSending(true)
    setError(null)
    try {
      const res = await cappeApi.post<CappeSocialChatTurn>(`/sites/${siteId}/social/chat/turns`, {
        conversation_id: conversationId, message, attachments,
      })
      setConversationId(res.conversation_id)
      save(siteId, res.conversation_id)
      setMessages((m) => [...m, res.message])
      if (res.plan) setCard(res.plan)
      loadChats()
    } catch (e) {
      // Put it back so nothing typed or dropped is lost.
      setMessages((m) => m.filter((x) => x.id !== mine.id))
      setText(message)
      setDrops(keptDrops)
      setError(e instanceof Error ? e.message : 'Couldn’t send that')
    } finally {
      setSending(false)
    }
  }

  const posterFor = (att: CappeSocialChatAttachment) =>
    att.kind === 'video' ? card?.plan.posts.flatMap((p) => p.media).find((m) => m.asset_id === att.asset_id)?.poster : att.url

  const list = (
    <ChatList chats={chats} current={conversationId} onOpen={(id) => void open(id)} onNew={newChat}
      onRename={(id, title) => void rename(id, title)} onDelete={(id) => void forget(id)} />
  )

  return (
    <div className="grid gap-4 sm:grid-cols-[13rem_minmax(0,1fr)]">
    <aside className="hidden max-h-[40rem] overflow-y-auto sm:block">{list}</aside>
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); void addFiles(e.dataTransfer.files) }}
      className={`min-w-0 rounded-2xl border p-4 transition ${dragging ? 'border-lime-400 bg-lime-400/5' : 'border-zinc-800 bg-zinc-900/60'}`}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-sm font-medium text-zinc-300"><Sparkles className="h-4 w-4 text-lime-400" /> Post with a message</span>
        <span className="flex items-center gap-3">
          <button type="button" onClick={() => setShowChats((v) => !v)} aria-expanded={showChats}
            className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 sm:hidden">
            <MessagesSquare className="h-3.5 w-3.5" /> Chats</button>
          {(messages.length > 0 || card) && (
            <button type="button" onClick={newChat} className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200">
              <MessageSquarePlus className="h-3.5 w-3.5" /> New chat</button>
          )}
        </span>
      </div>
      {showChats && <div className="mb-3 rounded-xl border border-zinc-800 p-2 sm:hidden">{list}</div>}

      {!aiReady && (
        <p className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/[0.06] px-3 py-2 text-xs text-amber-300">
          The assistant needs Claude set up on this server. You can still post with the form.
        </p>
      )}

      <div className="max-h-[32rem] space-y-3 overflow-y-auto">
        {loading && <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin text-zinc-500" /></div>}
        {!loading && messages.length === 0 && (
          <div className="py-6 text-center">
            <p className="text-sm text-zinc-300">Drop photos{videoOk ? ' or videos' : ''} here and say what you want — where, when, which product.</p>
            <div className="mt-3 flex flex-wrap justify-center gap-2">
              {EXAMPLES.map((ex) => (
                <button key={ex} type="button" onClick={() => setText(ex)}
                  className="rounded-full border border-zinc-700 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-800">{ex}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${m.role === 'user'
              ? 'bg-lime-400/15 text-zinc-100' : 'bg-zinc-800 text-zinc-200'}`}>
              {m.attachments.length > 0 && (
                <div className="mb-1.5 flex flex-wrap gap-1.5">
                  {m.attachments.map((a, i) => {
                    const src = posterFor(a)
                    return (
                      <div key={i} className="relative h-12 w-12 overflow-hidden rounded-md border border-zinc-700 bg-zinc-950" title={a.name ?? undefined}>
                        {src ? <img src={src} alt={a.name ?? ''} className="h-full w-full object-cover" />
                          : <Film className="m-auto mt-3.5 h-4 w-4 text-zinc-500" aria-hidden />}
                        {a.kind === 'video' && src && <Film className="absolute left-0.5 top-0.5 h-3 w-3 text-white drop-shadow" aria-hidden />}
                      </div>
                    )
                  })}
                </div>
              )}
              {m.content && <p className="whitespace-pre-wrap break-words">{m.content}</p>}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex items-center gap-2 text-xs text-zinc-400"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Planning…</div>
        )}
        {card && conversationId && (
          <PlanCard key={card.id} siteId={siteId} conversationId={conversationId} card={card} connections={connections}
            onDone={(next, message, where) => { setCard(next); loadChats(); if (message) onPosted(message, where) }} />
        )}
        <div ref={end} />
      </div>

      {drops.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {drops.map((d) => (
            <div key={d.key} className="relative h-16 w-16 overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950" title={d.error ?? d.name}>
              {d.kind === 'video' && !d.poster
                ? <video src={d.preview} muted playsInline aria-label={d.name} className="h-full w-full object-cover" />
                : <img src={d.url ?? d.poster ?? d.preview} alt={d.name} className="h-full w-full object-cover" />}
              {d.kind === 'video' && <Film className="absolute left-0.5 top-0.5 h-3 w-3 text-white drop-shadow" aria-hidden />}
              {d.uploading && (
                <span className="absolute inset-0 flex items-center justify-center bg-zinc-950/60 text-[10px] text-zinc-100">
                  {d.progress != null ? `${d.progress}%` : <Loader2 className="h-4 w-4 animate-spin" />}</span>
              )}
              {d.error && <span className="absolute inset-x-0 bottom-0 bg-red-600/90 px-0.5 text-[9px] text-white">Failed</span>}
              <button type="button" onClick={() => remove(d.key)} aria-label={`Remove ${d.name}`}
                className="absolute right-0.5 top-0.5 rounded-full bg-zinc-950/80 p-0.5 text-zinc-200"><X className="h-3 w-3" /></button>
            </div>
          ))}
        </div>
      )}

      {error && <p role="alert" className="mt-2 text-sm text-red-400">{error}</p>}
      <div className="mt-3 flex items-end gap-2">
        <button type="button" onClick={() => fileRef.current?.click()} aria-label="Attach photos or videos"
          className="rounded-lg border border-zinc-700 p-2 text-zinc-300 hover:bg-zinc-800"><Paperclip className="h-4 w-4" /></button>
        <input ref={fileRef} type="file" multiple className="hidden" aria-label="Attach files"
          accept={videoOk ? `${IMAGE_ACCEPT},${VIDEO_TYPES.join(',')}` : IMAGE_ACCEPT}
          onChange={(e) => { if (e.target.files) void addFiles(e.target.files); e.target.value = '' }} />
        <textarea value={text} rows={2} aria-label="Message" disabled={!aiReady}
          onChange={(e) => setText(e.target.value)}
          onPaste={(e) => { if (e.clipboardData.files.length) { e.preventDefault(); void addFiles(e.clipboardData.files) } }}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }}
          placeholder="e.g. Post these everywhere at 2pm tomorrow and link the oat latte"
          className="min-h-[2.75rem] flex-1 resize-y rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-lime-500 disabled:opacity-60" />
        <button type="button" onClick={send} disabled={sending || !aiReady} aria-label="Send"
          className="rounded-lg bg-lime-400 p-2.5 text-zinc-950 hover:bg-lime-300 disabled:opacity-60">
          {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </div>
    </div>
    </div>
  )
}
