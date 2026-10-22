import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Check, Copy, Download, Film, Loader2, Subtitles, Trash2, Upload } from 'lucide-react'
import { cappeApi } from '../../../api'
import type {
  CappeSocialExport, CappeSocialExportDownload, CappeSocialExportFile, CappeSocialExportPlatform,
  CappeSocialExportTarget, CappeSocialSettings,
} from '../../../types'
import { MAX_VIDEO_MB, uploadVideo, VIDEO_TYPES, videoProblem } from '../../../utils/socialVideo'

const PLATFORMS: [CappeSocialExportPlatform, string][] = [['instagram', 'Instagram'], ['tiktok', 'TikTok'], ['youtube', 'YouTube']]
const LABEL: Record<CappeSocialExportTarget, string> = {
  instagram: 'Instagram', tiktok: 'TikTok', youtube: 'YouTube', original: 'Original', captions: 'Captions (.srt)',
}
const BADGE: Record<string, [string, string]> = {
  queued: ['Waiting', 'bg-zinc-800 text-zinc-400'],
  working: ['Preparing', 'bg-violet-500/15 text-violet-300'],
  ready: ['Ready', 'bg-emerald-500/15 text-emerald-400'],
  partial: ['Some files failed', 'bg-orange-500/15 text-orange-400'],
  failed: ['Failed', 'bg-red-500/15 text-red-400'],
}
const STEP: Record<string, string> = {
  probe: 'Reading the video', transcribe: 'Listening for the words', encode: 'Cutting', srt: 'Writing the captions file',
}
const POLL_MS = 5000

function clock(ms: number | null): string {
  if (!ms) return ''
  const s = Math.round(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function fileNote(file: CappeSocialExportFile | null | undefined, open: boolean): string {
  if (!file) return open ? 'Being made…' : 'Not made'
  if (file.error) return file.error
  const size = file.width && file.height ? `${file.width}×${file.height}` : ''
  return [size, clock(file.duration_ms), file.trimmed ? 'first 3 minutes' : ''].filter(Boolean).join(' · ')
}

type CopyProps = { copied: string | null; onCopy: (id: string, text: string) => void }

function CopyButton({ id, text, label, copied, onCopy }: CopyProps & { id: string; text: string; label: string }) {
  return (
    <button type="button" onClick={() => onCopy(id, text)} aria-label={`Copy ${label}`}
      className="inline-flex shrink-0 items-center gap-1 rounded-md border border-zinc-700 px-2 py-1 text-[11px] text-zinc-300 hover:bg-zinc-800">
      {copied === id ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}{copied === id ? 'Copied' : 'Copy'}
    </button>
  )
}

/** The words to paste when uploading this platform's file. */
function Words({ exp, platform, ...copy }: CopyProps & { exp: CappeSocialExport; platform: CappeSocialExportPlatform }) {
  const id = `${exp.id}:${platform}`
  if (platform === 'youtube') {
    const yt = exp.texts.youtube
    if (!yt) return null
    return (
      <div className="mt-2 space-y-1.5 text-xs">
        {([['title', yt.title], ['description', yt.description], ['tags', yt.tags.join(', ')]] as const).filter(([, v]) => v).map(([name, value]) => (
          <div key={name} className="flex items-start gap-2">
            <div className="min-w-0 flex-1">
              <span className="text-zinc-500 capitalize">{name}</span>
              <p className="whitespace-pre-wrap break-words text-zinc-300">{value}</p>
            </div>
            <CopyButton id={`${id}:${name}`} text={value} label={`YouTube ${name}`} {...copy} />
          </div>
        ))}
      </div>
    )
  }
  const words = exp.texts[platform]
  if (!words?.text && !words?.link) return null
  return (
    <div className="mt-2 space-y-1.5 text-xs">
      {words.text && (
        <div className="flex items-start gap-2">
          <p className="min-w-0 flex-1 whitespace-pre-wrap break-words text-zinc-300">{words.text}</p>
          <CopyButton id={`${id}:caption`} text={words.text} label={`${LABEL[platform]} caption`} {...copy} />
        </div>
      )}
      {words.link && (
        <div className="flex items-start gap-2">
          <p className="min-w-0 flex-1 truncate text-zinc-500">Link for your bio: <span className="text-zinc-300">{words.link}</span></p>
          <CopyButton id={`${id}:link`} text={words.link} label={`${LABEL[platform]} link`} {...copy} />
        </div>
      )}
    </div>
  )
}

/** The files each video was cut into for Instagram, TikTok and YouTube, to
 *  download and upload from the phone, with the words to paste. TikTok and
 *  YouTube can't be posted to from here yet. Server side:
 *  routes/social_exports.py; the chat makes these too ("prepare this for all
 *  platforms"). */
export default function Exports({ siteId, settings, refreshKey, onCount }: {
  siteId: string
  settings: CappeSocialSettings | null
  refreshKey: number
  onCount?: (n: number) => void
}) {
  const [exports, setExports] = useState<CappeSocialExport[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const [platforms, setPlatforms] = useState<Set<CappeSocialExportPlatform>>(() => new Set(['instagram', 'tiktok', 'youtube']))
  const [captions, setCaptions] = useState(false)
  const [uploading, setUploading] = useState<{ name: string; progress: number | null } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const generation = useRef(0)
  const videoOk = !!settings?.video_available

  useEffect(() => {
    const gen = ++generation.current
    cappeApi.get<CappeSocialExport[]>(`/sites/${siteId}/social/exports`)
      .then((list) => { if (gen === generation.current) { setExports(list); setError(null) } })
      .catch((e) => { if (gen === generation.current) setError(e instanceof Error ? e.message : 'Couldn’t load your files') })
  }, [siteId, refreshKey, tick])

  const working = !!exports?.some((e) => e.status === 'queued' || e.status === 'working')
  useEffect(() => {
    if (!working) return
    const timer = setInterval(() => setTick((n) => n + 1), POLL_MS)
    return () => clearInterval(timer)
  }, [working])

  useEffect(() => { if (exports) onCount?.(exports.length) }, [exports, onCount])

  function togglePlatform(p: CappeSocialExportPlatform) {
    setPlatforms((s) => {
      const next = new Set(s)
      if (next.has(p)) next.delete(p)
      else next.add(p)
      return next
    })
  }

  async function prepare(file: File) {
    setError(null)
    const problem = videoProblem(file)
    if (problem) { setError(problem); return }
    if (!platforms.size) { setError('Pick at least one platform'); return }
    setUploading({ name: file.name, progress: null })
    try {
      const asset = await uploadVideo(siteId, file, (progress) => setUploading({ name: file.name, progress }))
      if (asset.status === 'failed') throw new Error(asset.error ?? 'We couldn’t read that video')
      const made = await cappeApi.post<CappeSocialExport>(`/sites/${siteId}/social/exports`, {
        asset_id: asset.id, platforms: PLATFORMS.map(([p]) => p).filter((p) => platforms.has(p)), captions,
      })
      setExports((list) => [made, ...(list ?? [])])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t prepare that video')
    } finally {
      setUploading(null)
    }
  }

  async function download(exp: CappeSocialExport, target: CappeSocialExportTarget) {
    setBusy(`${exp.id}:${target}`)
    setError(null)
    try {
      const res = await cappeApi.get<CappeSocialExportDownload>(
        `/sites/${siteId}/social/exports/${exp.id}/download?target=${target}`)
      window.location.assign(res.url)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t download that')
    } finally {
      setBusy(null)
    }
  }

  async function remove(exp: CappeSocialExport) {
    setBusy(`${exp.id}:delete`)
    try {
      await cappeApi.delete(`/sites/${siteId}/social/exports/${exp.id}`)
      setExports((list) => (list ?? []).filter((x) => x.id !== exp.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Couldn’t delete that')
    } finally {
      setBusy(null)
    }
  }

  async function copy(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(key)
      setTimeout(() => setCopied((k) => (k === key ? null : k)), 1500)
    } catch {
      setError('Couldn’t copy — select the text instead')
    }
  }

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4">
        <p className="text-sm text-zinc-300">
          TikTok and YouTube can’t be posted to from here yet, so each video gets a file made for each app. Download it, upload it from your phone, and paste the words.
        </p>
        {!videoOk ? (
          <p className="mt-3 text-xs text-amber-300">Video is part of the Business, Pro and Creator plans.</p>
        ) : (
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f && !uploading) void prepare(f) }}
            className="mt-3 space-y-3 rounded-xl border border-dashed border-zinc-700 p-4">
            <div className="flex flex-wrap items-center gap-2">
              {PLATFORMS.map(([p, label]) => (
                <button key={p} type="button" onClick={() => togglePlatform(p)} aria-pressed={platforms.has(p)}
                  className={`rounded-full px-3 py-1 text-xs font-medium ${platforms.has(p)
                    ? 'bg-lime-400 text-zinc-950' : 'border border-zinc-700 text-zinc-400 hover:text-zinc-200'}`}>{label}</button>
              ))}
              <label className="ml-1 inline-flex items-center gap-1.5 text-xs text-zinc-300">
                <input type="checkbox" checked={captions} onChange={(e) => setCaptions(e.target.checked)} className="accent-lime-400" />
                Burn in word-for-word captions
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" onClick={() => fileRef.current?.click()} disabled={!!uploading}
                className="inline-flex items-center gap-2 rounded-lg bg-lime-400 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-300 disabled:opacity-60">
                {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Prepare a video
              </button>
              <input ref={fileRef} type="file" accept={VIDEO_TYPES.join(',')} className="hidden" aria-label="Video to prepare"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void prepare(f); e.target.value = '' }} />
              <span className="text-xs text-zinc-500">
                {uploading ? `Uploading ${uploading.name}${uploading.progress != null ? ` · ${uploading.progress}%` : '…'}`
                  : `Or drop one here. Up to ${MAX_VIDEO_MB} MB; files use the first 3 minutes.`}
              </span>
            </div>
          </div>
        )}
      </div>

      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      {exports === null ? (
        !error && <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-zinc-500" /></div>
      ) : exports.length === 0 ? (
        <p className="py-6 text-center text-sm text-zinc-500">No files yet. Prepare a video here, or tell the chat “prepare this for all platforms”.</p>
      ) : exports.map((exp) => {
        const open = exp.status === 'queued' || exp.status === 'working'
        const [badge, tone] = BADGE[exp.status] ?? [exp.status, 'bg-zinc-800 text-zinc-400']
        const targets: CappeSocialExportTarget[] = [...exp.platforms, 'original', ...(exp.srt ? ['captions' as const] : [])]
        return (
          <section key={exp.id} aria-label={exp.filename ?? 'Video'} className="rounded-2xl border border-zinc-800 bg-zinc-900 p-4">
            <div className="flex items-start gap-3">
              <div className="relative h-16 w-12 shrink-0 overflow-hidden rounded-md border border-zinc-700 bg-zinc-950">
                {exp.poster ? <img src={exp.poster} alt="" className="h-full w-full object-cover" />
                  : <Film className="m-auto mt-5 h-5 w-5 text-zinc-500" aria-hidden />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="truncate text-sm font-medium text-zinc-100">{exp.filename ?? 'Video'}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}>{badge}</span>
                  {exp.captions && <span className="inline-flex items-center gap-1 text-[11px] text-zinc-400"><Subtitles className="h-3 w-3" /> Captions</span>}
                </div>
                <p className="mt-0.5 text-xs text-zinc-500">
                  {clock(exp.duration_ms)}
                  {open && ` · ${STEP[exp.progress.step ?? ''] ?? 'In line'}${exp.progress.total ? ` · ${exp.progress.done} of ${exp.progress.total} files` : ''}`}
                </p>
                {exp.error && <p className="mt-1 text-xs text-red-400">{exp.error}</p>}
                {exp.warnings.map((w) => (
                  <p key={w} className="mt-1 flex gap-1.5 text-xs text-amber-300"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{w}</p>
                ))}
              </div>
              <button type="button" onClick={() => void remove(exp)} disabled={busy === `${exp.id}:delete`} aria-label="Delete these files"
                className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"><Trash2 className="h-4 w-4" /></button>
            </div>
            <ul className="mt-3 divide-y divide-zinc-800 rounded-xl border border-zinc-800">
              {targets.map((t) => {
                const file = t === 'original' || t === 'captions' ? null : exp.files[t]
                const ready = t === 'original' ? exp.original : t === 'captions' ? exp.srt : !!file?.url
                const note = t === 'original' ? 'As uploaded' : t === 'captions' ? 'For YouTube’s captions' : fileNote(file, open)
                return (
                  <li key={t} className="px-3 py-2.5">
                    <div className="flex items-center gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="text-sm text-zinc-200">{LABEL[t]}</div>
                        <div className={`text-xs ${file?.error ? 'text-red-400' : 'text-zinc-500'}`}>{note}</div>
                      </div>
                      <button type="button" onClick={() => void download(exp, t)} disabled={!ready || busy === `${exp.id}:${t}`}
                        aria-label={`Download ${LABEL[t]}`}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-700 px-2.5 py-1.5 text-xs text-zinc-200 hover:bg-zinc-800 disabled:opacity-40">
                        {busy === `${exp.id}:${t}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />} Download
                      </button>
                    </div>
                    {t !== 'original' && t !== 'captions' && <Words exp={exp} platform={t} copied={copied} onCopy={(id, text) => void copy(id, text)} />}
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
