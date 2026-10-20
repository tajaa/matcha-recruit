import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, CalendarClock, ImagePlus, Loader2, Send, Sparkles, X } from 'lucide-react'
import { cappeApi } from '../../../api'
import type {
  CappeProduct, CappeSocialCaptionOption, CappeSocialCaptions, CappeSocialConnection, CappeSocialPost,
  CappeSocialPostInput, CappeSocialSettings, CappeSocialUpload,
} from '../../../types'
import {
  CAPTION_LIMIT, localInputToIso, nextSlot, scheduleError, spreadTimes, toLocalInput, withHashtags,
} from '../../../utils/socialSchedule'

type Photo = { key: string; name: string; preview: string; url: string | null; padded: boolean; error: string | null }
type Text = { caption: string; alt: string | null; options: CappeSocialCaptionOption[] | null; drafting: boolean }
type Group = { key: string; photos: Photo[] }
type When = 'now' | 'schedule' | 'draft'

const MAX_PER_POST = 10
const MAX_PHOTOS = 30
const UPLOADS_AT_ONCE = 3
const ACCEPT = 'image/jpeg,image/png,image/webp,image/gif'
const EMPTY: Text = { caption: '', alt: null, options: null, drafting: false }
let photoSeq = 0

export default function Composer({ siteId, connections, settings, metaConfigured, onPosted }: {
  siteId: string
  connections: CappeSocialConnection[]
  settings: CappeSocialSettings | null
  metaConfigured: boolean
  onPosted: (message: string) => void
}) {
  const [photos, setPhotos] = useState<Photo[]>([])
  const [mode, setMode] = useState<'together' | 'each'>('together')
  const [texts, setTexts] = useState<Record<string, Text>>({})
  const [picked, setPicked] = useState<Set<string> | null>(null)
  const [products, setProducts] = useState<CappeProduct[]>([])
  const [productId, setProductId] = useState('')
  const [link, setLink] = useState('')
  const [brief, setBrief] = useState('')
  const [when, setWhen] = useState<When>('schedule')
  const [start, setStart] = useState(() => toLocalInput(nextSlot()))
  const [everyDays, setEveryDays] = useState(1)
  const [dragging, setDragging] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const previews = useRef<Set<string>>(new Set())

  useEffect(() => {
    cappeApi.get<CappeProduct[]>(`/sites/${siteId}/products`)
      .then((list) => setProducts(list.filter((p) => p.status === 'active')))
      .catch(() => setProducts([]))
  }, [siteId])

  useEffect(() => {
    const urls = previews.current
    return () => urls.forEach((u) => URL.revokeObjectURL(u))
  }, [])

  const live = connections.filter((c) => c.status === 'connected')
  const chosen = picked ?? new Set(live.map((c) => c.id))
  const groups: Group[] = mode === 'together' ? [{ key: 'all', photos }] : photos.map((p) => ({ key: p.key, photos: [p] }))
  const textFor = (key: string) => texts[key] ?? EMPTY
  const setText = (key: string, patch: Partial<Text>) =>
    setTexts((t) => ({ ...t, [key]: { ...(t[key] ?? EMPTY), ...patch } }))
  const uploading = photos.some((p) => !p.url && !p.error)
  const tooMany = mode === 'together' && photos.length > MAX_PER_POST

  async function addFiles(files: FileList | File[]) {
    setError(null)
    const room = MAX_PHOTOS - photos.length
    const list = Array.from(files).filter((f) => f.type.startsWith('image/')).slice(0, Math.max(0, room))
    if (!list.length) return
    const fresh = list.map((file) => {
      const preview = URL.createObjectURL(file)
      previews.current.add(preview)
      return { file, photo: { key: `p${++photoSeq}`, name: file.name, preview, url: null, padded: false, error: null } }
    })
    setPhotos((p) => [...p, ...fresh.map((f) => f.photo)])
    let next = 0
    const worker = async () => {
      while (next < fresh.length) {
        const { file, photo } = fresh[next++]
        try {
          const fd = new FormData()
          fd.append('file', file)
          const res = await cappeApi.upload<CappeSocialUpload>(`/sites/${siteId}/social/media`, fd)
          setPhotos((ps) => ps.map((x) => (x.key === photo.key ? { ...x, url: res.url, padded: res.padded } : x)))
        } catch (e) {
          const message = e instanceof Error ? e.message : 'Upload failed'
          setPhotos((ps) => ps.map((x) => (x.key === photo.key ? { ...x, error: message } : x)))
        }
      }
    }
    await Promise.all(Array.from({ length: UPLOADS_AT_ONCE }, worker))
  }

  function remove(key: string) {
    setPhotos((ps) => {
      const gone = ps.find((p) => p.key === key)
      if (gone) { URL.revokeObjectURL(gone.preview); previews.current.delete(gone.preview) }
      return ps.filter((p) => p.key !== key)
    })
  }

  function move(key: string, by: -1 | 1) {
    setPhotos((ps) => {
      const i = ps.findIndex((p) => p.key === key)
      const j = i + by
      if (i < 0 || j < 0 || j >= ps.length) return ps
      const copy = [...ps]
      ;[copy[i], copy[j]] = [copy[j], copy[i]]
      return copy
    })
  }

  function switchMode(next: 'together' | 'each') {
    if (next === mode) return
    // Carry the shared caption over so nothing typed is lost.
    if (next === 'each') {
      const shared = textFor('all')
      setTexts((t) => {
        const out = { ...t }
        for (const p of photos) if (!out[p.key]?.caption) out[p.key] = { ...EMPTY, caption: shared.caption, alt: shared.alt }
        return out
      })
    } else if (!textFor('all').caption && photos[0]) {
      setText('all', { caption: textFor(photos[0].key).caption })
    }
    setMode(next)
  }

  async function draftCaptions(group: Group) {
    setError(null)
    setText(group.key, { drafting: true })
    try {
      const res = await cappeApi.post<CappeSocialCaptions>(`/sites/${siteId}/social/captions`, {
        media: group.photos.filter((p) => p.url).slice(0, 4).map((p) => ({ url: p.url, kind: 'image' })),
        product_id: productId || null,
        brief: brief.trim() || null,
      })
      setText(group.key, { options: res.options, alt: res.alt_text ?? textFor(group.key).alt, drafting: false })
    } catch (e) {
      setText(group.key, { drafting: false })
      setError(e instanceof Error ? e.message : 'Couldn’t write captions')
    }
  }

  function toggle(id: string) {
    const next = new Set(chosen)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setPicked(next)
  }

  function problem(): string | null {
    if (!groups.length || groups.every((g) => !g.photos.length && !textFor(g.key).caption.trim())) {
      return 'Drop a photo or write a caption first'
    }
    if (uploading) return 'Wait for the photos to finish uploading'
    if (photos.some((p) => p.error)) return 'Remove the photos that failed to upload'
    if (tooMany) return `One post can hold ${MAX_PER_POST} photos — post them one per photo instead`
    if (groups.some((g) => textFor(g.key).caption.length > CAPTION_LIMIT)) return `Captions are limited to ${CAPTION_LIMIT} characters`
    if (when !== 'draft' && !chosen.size) return 'Pick at least one account to post to'
    if (when !== 'draft' && !metaConfigured) return 'Instagram and Facebook aren’t set up on this server yet'
    if (when === 'schedule') return scheduleError(start)
    return null
  }

  async function submit() {
    const blocked = problem()
    if (blocked) { setError(blocked); return }
    setSaving(true)
    setError(null)
    // problem() has checked `start` is a real, future time.
    const first = new Date(localInputToIso(start) as string)
    const times = spreadTimes(first, groups.length, mode === 'each' ? everyDays : 1)
    const done: string[] = []
    try {
      for (const [i, group] of groups.entries()) {
        const text = textFor(group.key)
        const body: CappeSocialPostInput = {
          caption: text.caption.trim(),
          media: group.photos.map((p) => ({ url: p.url as string, kind: 'image', alt: text.alt })),
          connection_ids: [...chosen],
          scheduled_at: when === 'schedule' ? times[i].toISOString() : null,
          link_url: link.trim() || null,
          product_id: productId || null,
          alt_text: text.alt,
        }
        const post = await cappeApi.post<CappeSocialPost>(`/sites/${siteId}/social/posts`, body)
        if (when === 'now') await cappeApi.post(`/sites/${siteId}/social/posts/${post.id}/publish`)
        done.push(group.key)
      }
      photos.forEach((p) => { URL.revokeObjectURL(p.preview); previews.current.delete(p.preview) })
      setPhotos([])
      setTexts({})
      setBrief('')
      const n = groups.length
      onPosted(when === 'now' ? `Posting ${n === 1 ? 'your post' : `${n} posts`} now.`
        : when === 'schedule' ? `${n === 1 ? 'Post' : `${n} posts`} scheduled.` : `${n === 1 ? 'Draft' : `${n} drafts`} saved.`)
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Couldn’t save'
      // Drop what already went through, so trying again doesn't post it twice.
      if (done.length) {
        const doneKeys = new Set(mode === 'together' ? photos.map((p) => p.key) : done)
        setPhotos((ps) => ps.filter((p) => !doneKeys.has(p.key)))
      }
      setError(done.length ? `Saved ${done.length} of ${groups.length}. ${message}` : message)
    } finally {
      setSaving(false)
    }
  }

  const aiReady = settings?.ai_available !== false

  return (
    <div className="space-y-5">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); void addFiles(e.dataTransfer.files) }}
        className={`rounded-2xl border-2 border-dashed p-6 text-center transition ${
          dragging ? 'border-lime-400 bg-lime-400/5' : 'border-zinc-700 bg-zinc-900/60'}`}
      >
        <ImagePlus className="mx-auto mb-2 h-8 w-8 text-zinc-400" />
        <p className="text-sm text-zinc-300">Drop photos here, or{' '}
          <button type="button" onClick={() => fileRef.current?.click()} className="font-semibold text-lime-400 hover:underline">
            choose from your device</button>
        </p>
        <p className="mt-1 text-xs text-zinc-500">
          Up to {MAX_PHOTOS} photos. Each is resized and fitted for Instagram and Facebook automatically.
        </p>
        <input ref={fileRef} type="file" multiple accept={ACCEPT} className="hidden" aria-label="Choose photos"
          onChange={(e) => { if (e.target.files) void addFiles(e.target.files); e.target.value = '' }} />
      </div>

      {photos.length > 1 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-zinc-400">These {photos.length} photos are</span>
          {(['together', 'each'] as const).map((m) => (
            <button key={m} type="button" onClick={() => switchMode(m)} aria-pressed={mode === m}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${mode === m
                ? 'bg-lime-400 text-zinc-950' : 'border border-zinc-700 text-zinc-300 hover:bg-zinc-800'}`}>
              {m === 'together' ? 'one post (carousel)' : 'one post each'}
            </button>
          ))}
          {tooMany && <span className="text-xs text-amber-400">A carousel holds {MAX_PER_POST} at most.</span>}
        </div>
      )}

      {groups.length === 0 && (
        <GroupCard
          group={{ key: 'all', photos: [] }} index={0} total={1} text={textFor('all')} aiReady={aiReady}
          onText={(patch) => setText('all', patch)} onDraft={() => draftCaptions({ key: 'all', photos: [] })}
          onRemove={remove} onMove={move} reorder={false}
        />
      )}
      {groups.map((g, i) => (
        <GroupCard key={g.key} group={g} index={i} total={groups.length} text={textFor(g.key)} aiReady={aiReady}
          onText={(patch) => setText(g.key, patch)} onDraft={() => draftCaptions(g)} onRemove={remove} onMove={move}
          reorder={mode === 'together'} />
      ))}

      <div className="grid gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 sm:grid-cols-2">
        <div>
          <div className="mb-1.5 text-sm font-medium text-zinc-300">Post to</div>
          {live.length === 0 ? (
            <p className="text-xs text-zinc-500">No accounts connected yet — connect them under Accounts &amp; AI. You can still save drafts.</p>
          ) : (
            <div className="space-y-1.5">
              {live.map((c) => (
                <label key={c.id} className="flex items-center gap-2 text-sm text-zinc-200">
                  <input type="checkbox" checked={chosen.has(c.id)} onChange={() => toggle(c.id)} className="accent-lime-400" />
                  <span className="capitalize">{c.platform}</span>
                  <span className="text-zinc-500">{c.handle ? `@${c.handle}` : c.display_name}</span>
                </label>
              ))}
            </div>
          )}
        </div>
        <div className="space-y-3">
          <label className="block text-sm text-zinc-300">Product (helps the AI and your followers)
            <select value={productId} onChange={(e) => setProductId(e.target.value)}
              className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100">
              <option value="">None</option>
              {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label className="block text-sm text-zinc-300">Link (optional)
            <input value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://"
              className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600" />
          </label>
          {aiReady && (
            <label className="block text-sm text-zinc-300">What should the AI mention? (optional)
              <input value={brief} onChange={(e) => setBrief(e.target.value)} maxLength={500}
                placeholder="New fall menu, 20% off this weekend"
                className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600" />
            </label>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
        <div className="flex flex-wrap gap-2">
          {([['schedule', 'Schedule'], ['now', 'Post now'], ['draft', 'Save as draft']] as const).map(([w, label]) => (
            <button key={w} type="button" onClick={() => setWhen(w)} aria-pressed={when === w}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${when === w
                ? 'bg-lime-400 text-zinc-950' : 'border border-zinc-700 text-zinc-300 hover:bg-zinc-800'}`}>{label}</button>
          ))}
        </div>
        {when === 'schedule' && (
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <label className="text-sm text-zinc-300">{groups.length > 1 ? 'First post' : 'When'}
              <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)}
                className="mt-1 block rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100" />
            </label>
            {mode === 'each' && groups.length > 1 && (
              <label className="text-sm text-zinc-300">Then one every
                <select value={everyDays} onChange={(e) => setEveryDays(Number(e.target.value))}
                  className="mt-1 block rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100">
                  {[1, 2, 3, 7].map((d) => <option key={d} value={d}>{d === 1 ? 'day' : d === 7 ? 'week' : `${d} days`}</option>)}
                </select>
              </label>
            )}
          </div>
        )}
        {error && <p role="alert" className="mt-3 text-sm text-red-400">{error}</p>}
        <button type="button" onClick={submit} disabled={saving || uploading}
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-lime-400 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-300 disabled:opacity-60">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : when === 'schedule' ? <CalendarClock className="h-4 w-4" /> : <Send className="h-4 w-4" />}
          {when === 'schedule' ? (groups.length > 1 ? `Schedule ${groups.length} posts` : 'Schedule post')
            : when === 'now' ? (groups.length > 1 ? `Post ${groups.length} now` : 'Post now') : 'Save draft'}
        </button>
      </div>
    </div>
  )
}

function GroupCard({ group, index, total, text, aiReady, onText, onDraft, onRemove, onMove, reorder }: {
  group: Group
  index: number
  total: number
  text: Text
  aiReady: boolean
  onText: (patch: Partial<Text>) => void
  onDraft: () => void
  onRemove: (key: string) => void
  onMove: (key: string, by: -1 | 1) => void
  reorder: boolean
}) {
  const ready = group.photos.length > 0 && group.photos.every((p) => p.url)
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
      {total > 1 && <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">Post {index + 1} of {total}</div>}
      {group.photos.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {group.photos.map((p, i) => (
            <div key={p.key} className="relative h-24 w-24 overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950">
              <img src={p.url ?? p.preview} alt={p.name} className={`h-full w-full object-cover ${p.url ? '' : 'opacity-50'}`} />
              {!p.url && !p.error && <Loader2 className="absolute inset-0 m-auto h-5 w-5 animate-spin text-zinc-200" />}
              {p.error && <div className="absolute inset-x-0 bottom-0 bg-red-600/90 px-1 py-0.5 text-[10px] text-white" title={p.error}>Failed</div>}
              {p.padded && <div className="absolute inset-x-0 bottom-0 bg-zinc-950/80 px-1 py-0.5 text-[10px] text-zinc-300" title="White bars were added so it fits Instagram">Fitted</div>}
              <button type="button" onClick={() => onRemove(p.key)} aria-label={`Remove ${p.name}`}
                className="absolute right-1 top-1 rounded-full bg-zinc-950/80 p-0.5 text-zinc-200 hover:text-white"><X className="h-3.5 w-3.5" /></button>
              {reorder && group.photos.length > 1 && (
                <div className="absolute bottom-1 left-1 flex gap-0.5">
                  <button type="button" disabled={i === 0} onClick={() => onMove(p.key, -1)} aria-label="Move earlier"
                    className="rounded bg-zinc-950/80 p-0.5 text-zinc-200 disabled:opacity-30"><ArrowLeft className="h-3 w-3" /></button>
                  <button type="button" disabled={i === group.photos.length - 1} onClick={() => onMove(p.key, 1)} aria-label="Move later"
                    className="rounded bg-zinc-950/80 p-0.5 text-zinc-200 disabled:opacity-30"><ArrowRight className="h-3 w-3" /></button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={`caption-${group.key}`} className="text-sm font-medium text-zinc-300">Caption</label>
        {aiReady && (
          <button type="button" onClick={onDraft} disabled={text.drafting || (group.photos.length > 0 && !ready)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-2.5 py-1 text-xs font-medium text-lime-300 hover:bg-zinc-800 disabled:opacity-50">
            {text.drafting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
            Write with AI
          </button>
        )}
      </div>
      <textarea id={`caption-${group.key}`} value={text.caption} onChange={(e) => onText({ caption: e.target.value })} rows={4}
        placeholder="Say something about it…"
        className="mt-1.5 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-lime-500" />
      <div className={`text-right text-xs ${text.caption.length > CAPTION_LIMIT ? 'text-red-400' : 'text-zinc-500'}`}>
        {text.caption.length}/{CAPTION_LIMIT}
      </div>
      {text.options && text.options.length > 0 && (
        <div className="mt-2 grid gap-2 sm:grid-cols-3">
          {text.options.map((o, i) => (
            <button key={i} type="button" onClick={() => onText({ caption: withHashtags(o.text, o.hashtags) })}
              className="rounded-xl border border-zinc-700 bg-zinc-950 p-3 text-left text-xs text-zinc-300 hover:border-lime-500">
              <span className="line-clamp-5 whitespace-pre-wrap">{o.text}</span>
              {o.hashtags.length > 0 && <span className="mt-1.5 block text-lime-400/80">{o.hashtags.join(' ')}</span>}
              <span className="mt-2 block font-semibold text-lime-300">Use this</span>
            </button>
          ))}
        </div>
      )}
      {group.photos.length > 0 && (
        <label className="mt-3 block text-xs text-zinc-400">Photo description for screen readers
          <input value={text.alt ?? ''} onChange={(e) => onText({ alt: e.target.value || null })} maxLength={500}
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100" />
        </label>
      )}
    </div>
  )
}
