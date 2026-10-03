import { useEffect, useState } from 'react'
import { Check, Loader2, Upload } from 'lucide-react'
import { Card, Button } from '../ui'
import { landingMedia } from '../../api/admin/landingMedia'
import { EMPTY_COMMERCIAL, type CommercialSlot, type SchedulingCommercial } from '../../types/landingMedia'

const SLOTS: { slot: CommercialSlot; label: string; note: string; accept: string; max: number }[] = [
  { slot: 'desktop_video', label: 'Desktop commercial', note: 'Landscape 16:9 · MP4 or WebM · up to 150 MB', accept: 'video/mp4,video/webm', max: 150 },
  { slot: 'mobile_video', label: 'Mobile commercial', note: 'Vertical 9:16 · MP4 or WebM · up to 150 MB', accept: 'video/mp4,video/webm', max: 150 },
  { slot: 'desktop_poster', label: 'Desktop poster', note: 'Landscape 16:9 · JPG, PNG, or WebP · up to 5 MB', accept: 'image/jpeg,image/png,image/webp', max: 5 },
  { slot: 'mobile_poster', label: 'Mobile poster', note: 'Vertical 9:16 · JPG, PNG, or WebP · up to 5 MB', accept: 'image/jpeg,image/png,image/webp', max: 5 },
  { slot: 'captions', label: 'English captions', note: 'WebVTT (.vtt) · same timing for both edits · up to 1 MB', accept: '.vtt,text/vtt', max: 1 },
]

export function SchedulingCommercialSettings() {
  const [draft, setDraft] = useState<SchedulingCommercial>(EMPTY_COMMERCIAL)
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState<CommercialSlot | null>(null)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const busy = saving || uploading !== null

  useEffect(() => {
    let active = true
    landingMedia.getAdmin().then((data) => {
      if (active) { setDraft({ ...EMPTY_COMMERCIAL, ...data.scheduling_commercial }); setLoaded(true) }
    }).catch((err: unknown) => { if (active) setError(err instanceof Error ? err.message : 'Could not load the commercial settings.') })
    return () => { active = false }
  }, [])

  async function upload(file: File, item: typeof SLOTS[number]) {
    if (file.size === 0 || file.size > item.max * 1024 * 1024) { setError(`Choose a file between 1 byte and ${item.max} MB.`); return }
    setUploading(item.slot)
    setProgress(0)
    setError(null)
    setMessage(null)
    try {
      const url = await landingMedia.uploadCommercial(file, item.slot, setProgress)
      setDraft((current) => ({ ...current, [`${item.slot}_url`]: url }))
      setMessage('Upload complete. Preview the file, then save the commercial settings.')
    } catch (err) { setError(err instanceof Error ? err.message : 'Upload failed.') }
    finally { setUploading(null) }
  }

  async function save() {
    setSaving(true)
    setError(null)
    setMessage(null)
    try {
      const result = await landingMedia.saveCommercial(draft)
      setDraft(result.value)
      setMessage(result.value.enabled ? 'Commercial enabled on /scheduling-v2.' : 'Commercial settings saved. The commercial is disabled.')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save the commercial.') }
    finally { setSaving(false) }
  }

  return (
    <Card>
      <div className="space-y-6 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-200">Scheduling commercial</h2><p className="mt-2 max-w-xl text-sm leading-relaxed text-zinc-400">Upload the film for /scheduling-v2. Visitors can watch with sound, seek with the player controls, or skip to the schedule. Files upload directly to your public media S3 bucket.</p></div>
          <Button type="button" disabled={!loaded || busy || (draft.enabled && !draft.desktop_video_url)} onClick={save}>{saving ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}Save commercial</Button>
        </div>
        {!loaded && !error && <p className="text-sm text-zinc-400">Loading commercial settings…</p>}
        {error && <p role="alert" className="rounded border border-red-900/40 bg-red-950/20 p-3 text-sm text-red-300">{error}</p>}
        {message && <p role="status" className="text-sm text-emerald-400">{message}</p>}
        <label className="flex items-center gap-3 text-sm text-zinc-200"><input type="checkbox" checked={draft.enabled} disabled={!loaded || busy || !draft.desktop_video_url} onChange={(event) => setDraft((current) => ({ ...current, enabled: event.target.checked }))} />Show the commercial on the scheduling preview</label>
        <p className="text-xs leading-relaxed text-zinc-500">Upload the desktop edit first. A separate vertical edit keeps the app readable on phones; mobile falls back to the desktop film if absent. Use MP4 with H.264 video and AAC audio for broad compatibility. Poster images appear before playback. Upload captions when the film includes speech.</p>
        <div className="space-y-5">
          {SLOTS.map((item) => {
            const key = `${item.slot}_url` as keyof Omit<SchedulingCommercial, 'enabled'>
            const url = draft[key]
            const isVideo = item.slot.endsWith('_video')
            const isPoster = item.slot.endsWith('_poster')
            return (
              <div key={item.slot} className="border-t border-zinc-800 pt-5">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div><h3 className="text-sm font-medium text-zinc-200">{item.label}</h3><p className="mt-1 text-xs text-zinc-500">{item.note}</p></div>
                  <div className="flex items-center gap-3">
                    <label className={`inline-flex items-center gap-2 rounded bg-zinc-800 px-3 py-2 text-sm text-zinc-100 ${!loaded || busy ? 'opacity-50' : 'cursor-pointer hover:bg-zinc-700'}`}>
                      {uploading === item.slot ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {url ? 'Replace' : 'Upload'}
                      <input aria-label={`Upload ${item.label.toLowerCase()}`} type="file" accept={item.accept} disabled={!loaded || busy} className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file, item); event.target.value = '' }} />
                    </label>
                    {url && <button type="button" disabled={busy} className="text-xs text-zinc-400 hover:text-red-300" onClick={() => setDraft((current) => ({ ...current, [key]: null, ...(item.slot === 'desktop_video' ? { enabled: false } : {}) }))}>Clear</button>}
                  </div>
                </div>
                {uploading === item.slot && <div className="mt-3"><progress aria-label={`${item.label} upload progress`} value={progress} max={100} className="h-2 w-full" /><p role="status" className="mt-1 text-xs text-zinc-400">{progress < 100 ? `Uploading ${progress}%` : 'Verifying upload…'}</p></div>}
                {url && isVideo && <video src={url} controls playsInline crossOrigin={draft.captions_url ? 'anonymous' : undefined} preload="metadata" poster={draft[item.slot === 'desktop_video' ? 'desktop_poster_url' : 'mobile_poster_url'] ?? undefined} className={`mt-4 max-h-80 rounded bg-black object-contain ${item.slot === 'mobile_video' ? 'aspect-[9/16] w-44' : 'aspect-video w-full max-w-xl'}`}>{draft.captions_url && <track kind="captions" src={draft.captions_url} srcLang="en" label="English" />}</video>}
                {url && isPoster && <img src={url} alt={`${item.label} preview`} className="mt-4 max-h-40 max-w-xs rounded object-contain" />}
                {url && item.slot === 'captions' && <a href={url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs text-zinc-400 underline">Preview caption file</a>}
              </div>
            )
          })}
        </div>
      </div>
    </Card>
  )
}
