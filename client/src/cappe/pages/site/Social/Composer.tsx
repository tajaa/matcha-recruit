import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, CalendarClock, Film, ImagePlus, Loader2, Send, Sparkles, X } from 'lucide-react'
import { cappeApi } from '../../../api'
import type {
  CappeProduct, CappeSocialAsset, CappeSocialCaptionOption, CappeSocialCaptions, CappeSocialConnection,
  CappeSocialMedia, CappeSocialPost, CappeSocialPostInput, CappeSocialSettings, CappeSocialUpload,
} from '../../../types'
import {
  CAPTION_LIMIT, localInputToIso, nextSlot, scheduleError, spreadTimes, toLocalInput, withHashtags,
} from '../../../utils/socialSchedule'
import { MAX_VIDEO_MB, posterOf, uploadVideo, VIDEO_TYPES, videoProblem } from '../../../utils/socialVideo'

// A dropped photo or video. A photo is ready once it has its `url`; a video
// once the server has it (`assetId`) — it may still be `rendering` (being cut
// to size), which is fine to schedule: the post waits for it.
type Photo = {
  key: string
  name: string
  kind: 'image' | 'video'
  preview: string
  url: string | null
  assetId: string | null
  poster: string | null
  status: 'uploading' | 'rendering' | 'ready' | 'failed'
  progress: number | null
  padded: boolean
  trimmed: boolean
  error: string | null
}
type Text = { caption: string; alt: string | null; options: CappeSocialCaptionOption[] | null; drafting: boolean }
type Group = { key: string; photos: Photo[] }
type When = 'now' | 'schedule' | 'draft'

const MAX_PER_POST = 10
const MAX_PHOTOS = 30
const MAX_VIDEOS = 5
const UPLOADS_AT_ONCE = 3
const POLL_MS = 3000
const IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp,image/gif'
const EMPTY: Text = { caption: '', alt: null, options: null, drafting: false }
let photoSeq = 0

function fromAsset(asset: CappeSocialAsset): Partial<Photo> {
  if (asset.status === 'failed' || asset.status === 'deleted') {
    return { status: 'failed', error: asset.error ?? 'We couldn’t prepare that video' }
  }
  return { assetId: asset.id, status: asset.status === 'ready' ? 'ready' : 'rendering', poster: posterOf(asset),
    trimmed: asset.trimmed, progress: null }
}

/** What the AI looks at for an item: the photo, or the video's poster frame. */
const pictureOf = (p: Photo) => (p.kind === 'image' ? p.url : p.poster)

export default function Composer({ siteId, connections, settings, metaConfigured, onPosted }: {
  siteId: string
  connections: CappeSocialConnection[]
  settings: CappeSocialSettings | null
  metaConfigured: boolean
  onPosted: (message: string) => void
}) {
  const [photos, setPhotos] = useState<Photo[]>([])
  const videoOk = !!settings?.video_available
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

  // While any video is being cut, check on it so its poster and status show.
  const renderingKey = photos.filter((p) => p.status === 'rendering' && p.assetId).map((p) => p.assetId).join(',')
  useEffect(() => {
    if (!renderingKey) return
    const timer = setInterval(() => {
      for (const assetId of renderingKey.split(',')) {
        cappeApi.get<CappeSocialAsset>(`/sites/${siteId}/social/assets/${assetId}`)
          .then((asset) => setPhotos((ps) => ps.map((x) => (x.assetId === assetId ? { ...x, ...fromAsset(asset) } : x))))
          .catch(() => {})
      }
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [renderingKey, siteId])

  const live = connections.filter((c) => c.status === 'connected')
  const chosen = picked ?? new Set(live.map((c) => c.id))
  const images = photos.filter((p) => p.kind === 'image')
  const videos = photos.filter((p) => p.kind === 'video')
  // Photos can share a carousel; a video always goes out on its own (as a Reel).
  const groups: Group[] = mode === 'together'
    ? (videos.length
        ? [
            ...(images.length ? [{ key: 'all', photos: images }] : []),
            ...videos.map((v, i) => ({ key: !images.length && i === 0 ? 'all' : v.key, photos: [v] })),
          ]
        : [{ key: 'all', photos: images }])
    : photos.map((p) => ({ key: p.key, photos: [p] }))
  const textFor = (key: string) => texts[key] ?? EMPTY
  const setText = (key: string, patch: Partial<Text>) =>
    setTexts((t) => ({ ...t, [key]: { ...(t[key] ?? EMPTY), ...patch } }))
  const uploading = photos.some((p) => p.status === 'uploading' && !p.error)
  const preparing = videos.some((p) => p.status === 'rendering')
  const tooMany = mode === 'together' && images.length > MAX_PER_POST

  function update(key: string, patch: Partial<Photo>) {
    setPhotos((ps) => ps.map((x) => (x.key === key ? { ...x, ...patch } : x)))
  }

  function newItem(file: File, kind: Photo['kind']): Photo {
    const preview = URL.createObjectURL(file)
    previews.current.add(preview)
    return { key: `p${++photoSeq}`, name: file.name, kind, preview, url: null, assetId: null, poster: null,
      status: 'uploading', progress: null, padded: false, trimmed: false, error: null }
  }

  async function addVideos(files: File[]) {
    const room = Math.min(MAX_VIDEOS - videos.length, MAX_PHOTOS - photos.length)
    const added = files.slice(0, Math.max(0, room)).map((file) => ({ file, photo: newItem(file, 'video') }))
    if (!added.length) return
    setPhotos((p) => [...p, ...added.map((a) => a.photo)])
    // One at a time: a phone clip is big, and the first one is ready soonest.
    for (const { file, photo } of added) {
      const problem = videoProblem(file)
      if (problem) { update(photo.key, { status: 'failed', error: problem }); continue }
      try {
        const asset = await uploadVideo(siteId, file, (progress) => update(photo.key, { progress }))
        update(photo.key, fromAsset(asset))
      } catch (e) {
        update(photo.key, { status: 'failed', error: e instanceof Error ? e.message : 'Upload failed' })
      }
    }
  }

  async function addFiles(files: FileList | File[]) {
    setError(null)
    const all = Array.from(files)
    const dropped = all.filter((f) => f.type.startsWith('video/'))
    if (dropped.length && !videoOk) setError('Video posts are part of the Business, Pro and Creator plans.')
    const room = MAX_PHOTOS - photos.length
    const list = all.filter((f) => f.type.startsWith('image/')).slice(0, Math.max(0, room))
    const pending = videoOk && dropped.length ? addVideos(dropped) : Promise.resolve()
    if (!list.length) { await pending; return }
    const fresh = list.map((file) => ({ file, photo: newItem(file, 'image') }))
    setPhotos((p) => [...p, ...fresh.map((f) => f.photo)])
    let next = 0
    const worker = async () => {
      while (next < fresh.length) {
        const { file, photo } = fresh[next++]
        try {
          const fd = new FormData()
          fd.append('file', file)
          const res = await cappeApi.upload<CappeSocialUpload>(`/sites/${siteId}/social/media`, fd)
          update(photo.key, { url: res.url, padded: res.padded, status: 'ready' })
        } catch (e) {
          update(photo.key, { status: 'failed', error: e instanceof Error ? e.message : 'Upload failed' })
        }
      }
    }
    await Promise.all([pending, ...Array.from({ length: UPLOADS_AT_ONCE }, worker)])
  }

  function remove(key: string) {
    const gone = photos.find((p) => p.key === key)
    if (gone) {
      URL.revokeObjectURL(gone.preview)
      previews.current.delete(gone.preview)
      // A video no post uses yet is dropped on the server too.
      if (gone.assetId) void cappeApi.delete(`/sites/${siteId}/social/assets/${gone.assetId}`).catch(() => {})
    }
    setPhotos((ps) => ps.filter((p) => p.key !== key))
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
        media: group.photos.map(pictureOf).filter(Boolean).slice(0, 4).map((url) => ({ url, kind: 'image' })),
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
    if (uploading) return 'Wait for the uploads to finish'
    if (photos.some((p) => p.error)) return 'Remove the files that failed to upload'
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
    // "One post each" spreads the posts; "together" (a carousel plus any
    // videos, which always post on their own) all go out at the time picked.
    const times = mode === 'each' ? spreadTimes(first, groups.length, everyDays) : groups.map(() => first)
    const done: string[] = []
    try {
      for (const [i, group] of groups.entries()) {
        const text = textFor(group.key)
        const body: CappeSocialPostInput = {
          caption: text.caption.trim(),
          media: group.photos.map((p): CappeSocialMedia => (p.kind === 'video'
            ? { kind: 'video', asset_id: p.assetId, alt: text.alt }
            : { url: p.url, kind: 'image', alt: text.alt })),
          connection_ids: [...chosen],
          scheduled_at: when === 'schedule' ? times[i].toISOString() : null,
          link_url: link.trim() || null,
          product_id: productId || null,
          alt_text: text.alt,
        }
        const post = await cappeApi.post<CappeSocialPost>(`/sites/${siteId}/social/posts`, body)
        // Saved counts as done even if Post now fails next: trying again
        // must not make a second copy (it is in the Queue to retry).
        done.push(group.key)
        if (when === 'now') await cappeApi.post(`/sites/${siteId}/social/posts/${post.id}/publish`)
      }
      photos.forEach((p) => { URL.revokeObjectURL(p.preview); previews.current.delete(p.preview) })
      setPhotos([])
      setTexts({})
      setBrief('')
      const n = groups.length
      const wait = preparing && when !== 'draft' ? ' Videos go out once they’re ready.' : ''
      onPosted((when === 'now' ? `Posting ${n === 1 ? 'your post' : `${n} posts`} now.`
        : when === 'schedule' ? `${n === 1 ? 'Post' : `${n} posts`} scheduled.` : `${n === 1 ? 'Draft' : `${n} drafts`} saved.`) + wait)
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Couldn’t save'
      // Drop what already went through, so trying again doesn't post it twice.
      if (done.length) {
        const doneKeys = new Set(groups.filter((g) => done.includes(g.key)).flatMap((g) => g.photos.map((p) => p.key)))
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
        <p className="text-sm text-zinc-300">{videoOk ? 'Drop photos or videos here' : 'Drop photos here'}, or{' '}
          <button type="button" onClick={() => fileRef.current?.click()} className="font-semibold text-lime-400 hover:underline">
            choose from your device</button>
        </p>
        <p className="mt-1 text-xs text-zinc-500">
          Up to {MAX_PHOTOS} photos. Each is resized and fitted for Instagram and Facebook automatically.
          {videoOk && ` Videos (up to ${MAX_VIDEO_MB} MB; posts use the first 90 seconds) are cut to size and posted as Reels.`}
        </p>
        <input ref={fileRef} type="file" multiple accept={videoOk ? `${IMAGE_ACCEPT},${VIDEO_TYPES.join(',')}` : IMAGE_ACCEPT}
          className="hidden" aria-label={videoOk ? 'Choose photos or videos' : 'Choose photos'}
          onChange={(e) => { if (e.target.files) void addFiles(e.target.files); e.target.value = '' }} />
      </div>

      {images.length > 1 && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-zinc-400">These {images.length} photos are</span>
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
  // The AI needs a picture of each item: the photo, or a video's poster frame.
  const ready = group.photos.length > 0 && group.photos.every((p) => pictureOf(p))
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
      {total > 1 && <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">Post {index + 1} of {total}</div>}
      {group.photos.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {group.photos.map((p, i) => (
            <div key={p.key} className="relative h-24 w-24 overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950">
              {p.kind === 'video' && !p.poster
                ? <video src={p.preview} muted playsInline aria-label={p.name}
                    className={`h-full w-full object-cover ${p.status === 'uploading' ? 'opacity-50' : ''}`} />
                : <img src={p.url ?? p.poster ?? p.preview} alt={p.name}
                    className={`h-full w-full object-cover ${p.status === 'uploading' ? 'opacity-50' : ''}`} />}
              {p.kind === 'video' && <Film className="absolute left-1 top-1 h-3.5 w-3.5 text-white drop-shadow" aria-hidden />}
              {p.status === 'uploading' && !p.error && (p.progress != null
                ? <span className="absolute inset-0 m-auto h-fit w-fit rounded bg-zinc-950/80 px-1.5 text-xs text-zinc-100">{p.progress}%</span>
                : <Loader2 className="absolute inset-0 m-auto h-5 w-5 animate-spin text-zinc-200" />)}
              {p.error && <div className="absolute inset-x-0 bottom-0 bg-red-600/90 px-1 py-0.5 text-[10px] text-white" title={p.error}>Failed</div>}
              {!p.error && p.status === 'rendering' && (
                <div className="absolute inset-x-0 bottom-0 bg-zinc-950/80 px-1 py-0.5 text-[10px] text-zinc-300"
                  title="Cutting it to size for Reels — you can schedule it now">Preparing…</div>
              )}
              {!p.error && p.status === 'ready' && p.trimmed && (
                <div className="absolute inset-x-0 bottom-0 bg-zinc-950/80 px-1 py-0.5 text-[10px] text-zinc-300"
                  title="Reels take up to 90 seconds, so the rest was left out">First 90 s</div>
              )}
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
        <label className="mt-3 block text-xs text-zinc-400">Description for screen readers
          <input value={text.alt ?? ''} onChange={(e) => onText({ alt: e.target.value || null })} maxLength={500}
            className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100" />
        </label>
      )}
    </div>
  )
}
