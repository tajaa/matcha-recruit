import { useEffect, useRef, useState } from 'react'
import { Check, Loader2, Upload } from 'lucide-react'
import { Card, Button } from '../ui'
import { landingMedia } from '../../api/admin/landingMedia'
import { EMPTY_COMMERCIAL, type CommercialSlot, type CommercialUploadProgress, type SchedulingCommercial } from '../../types/landingMedia'

const SLOTS: { slot: CommercialSlot; label: string; note: string; accept: string; max: number }[] = [
  { slot: 'desktop_video', label: 'Desktop commercial', note: 'Landscape 16:9 · MP4 or WebM · up to 150 MB', accept: 'video/mp4,video/webm', max: 150 },
  { slot: 'mobile_video', label: 'Mobile commercial', note: 'Vertical 9:16 · MP4 or WebM · up to 150 MB', accept: 'video/mp4,video/webm', max: 150 },
  { slot: 'desktop_poster', label: 'Desktop poster', note: 'Landscape 16:9 · JPG, PNG, or WebP · up to 5 MB', accept: 'image/jpeg,image/png,image/webp', max: 5 },
  { slot: 'mobile_poster', label: 'Mobile poster', note: 'Vertical 9:16 · JPG, PNG, or WebP · up to 5 MB', accept: 'image/jpeg,image/png,image/webp', max: 5 },
  { slot: 'captions', label: 'English captions', note: 'WebVTT (.vtt) · same timing for both edits · up to 1 MB', accept: '.vtt,text/vtt', max: 1 },
]

export function SchedulingCommercialSettings() {
  const fileInputs = useRef<Partial<Record<CommercialSlot, HTMLInputElement | null>>>({})
  const [draft, setDraft] = useState<SchedulingCommercial>(EMPTY_COMMERCIAL)
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState<CommercialSlot | null>(null)
  const [progress, setProgress] = useState<CommercialUploadProgress>({ phase: 'preparing', percent: null })
  const [selectedFile, setSelectedFile] = useState<{ name: string; size: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const busy = saving || uploading !== null

  useEffect(() => {
    let active = true
    landingMedia.getAdmin().then((data) => {
      if (!data.scheduling_commercial) throw new Error('Commercial uploads are unavailable on this server. Update the server and reload this page.')
      if (active) { setDraft({ ...EMPTY_COMMERCIAL, ...data.scheduling_commercial }); setLoaded(true) }
    }).catch((err: unknown) => { if (active) setError(err instanceof Error ? err.message : 'Could not load the commercial settings.') })
    return () => { active = false }
  }, [])

  async function upload(file: File, item: typeof SLOTS[number]) {
    setError(null)
    setMessage(null)
    if (file.size === 0 || file.size > item.max * 1024 * 1024) { setError(`${file.name}: choose a file between 1 byte and ${item.max} MB. Resolution alone does not determine file size.`); return }
    const ext = file.name.split('.').pop()?.toLowerCase()
    const extensions = item.slot === 'captions' ? ['vtt'] : item.slot.endsWith('_video') ? ['mp4', 'webm'] : ['jpg', 'jpeg', 'png', 'webp']
    if (!ext || !extensions.includes(ext)) { setError(`${file.name}: choose ${extensions.map((value) => value.toUpperCase()).join(' or ')}.${item.slot.endsWith('_video') ? ' Export video as MP4 with H.264 video and AAC audio.' : ''}`); return }
    setUploading(item.slot)
    setSelectedFile({ name: file.name, size: file.size })
    setProgress({ phase: 'preparing', percent: null })
    try {
      const url = await landingMedia.uploadCommercial(file, item.slot, setProgress)
      setDraft((current) => ({ ...current, [`${item.slot}_url`]: url }))
      setMessage(`${file.name} uploaded and verified. Preview it, enable the commercial when ready, then choose Save commercial to publish on the home page.`)
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
      setMessage(result.value.enabled ? 'Commercial enabled on the home page.' : 'Commercial settings saved. The commercial is disabled.')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save the commercial.') }
    finally { setSaving(false) }
  }

  return (
    <Card>
      <div className="space-y-6 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-200">Scheduling commercial</h2><p className="mt-2 max-w-xl text-sm leading-relaxed text-zinc-400">Upload a desktop film, preview it, turn on the checkbox, then save. The film appears on the <a href="/" target="_blank" rel="noreferrer" className="underline">home page</a>. Uploading alone does not publish it.</p></div>
          <Button type="button" disabled={!loaded || busy || (draft.enabled && !draft.desktop_video_url)} onClick={save}>{saving ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}Save commercial</Button>
        </div>
        {!loaded && !error && <p className="text-sm text-zinc-400">Loading commercial settings…</p>}
        {error && <p role="alert" className="rounded border border-red-900/40 bg-red-950/20 p-3 text-sm text-red-300">{error}</p>}
        {message && <p role="status" className="text-sm text-emerald-400">{message}</p>}
        <label className="flex items-center gap-3 text-sm text-zinc-200"><input type="checkbox" checked={draft.enabled} disabled={!loaded || busy || !draft.desktop_video_url} onChange={(event) => setDraft((current) => ({ ...current, enabled: event.target.checked }))} />Show the commercial on the home page</label>
        <p className="text-xs leading-relaxed text-zinc-500">1080p is supported: export MP4 with H.264 video and AAC audio, up to 150 MB. Transfer progress appears below the selected file; verification finishes before a preview is added. A separate vertical edit keeps the app readable on phones; mobile falls back to the desktop film if absent. Upload posters and captions when needed.</p>
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
                    <Button type="button" variant="secondary" aria-label={`${url ? 'Replace' : 'Upload'} ${item.label.toLowerCase()}`} disabled={!loaded || busy} onClick={() => fileInputs.current[item.slot]?.click()} className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-900">
                      {uploading === item.slot ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {url ? 'Replace' : 'Upload'}
                    </Button>
                    <input ref={(element) => { fileInputs.current[item.slot] = element }} aria-label={`Choose ${item.label.toLowerCase()} file`} type="file" accept={item.accept} disabled={!loaded || busy} hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file, item); event.target.value = '' }} />
                    {url && <button type="button" disabled={busy} className="text-xs text-zinc-400 hover:text-red-300" onClick={() => setDraft((current) => ({ ...current, [key]: null, ...(item.slot === 'desktop_video' ? { enabled: false } : {}) }))}>Clear</button>}
                  </div>
                </div>
                {uploading === item.slot && <div className="mt-4 rounded-lg border border-zinc-700 bg-zinc-900 p-4">
                  <p className="break-all text-sm text-zinc-200">{selectedFile?.name}<span className="ml-2 whitespace-nowrap text-xs text-zinc-400">{selectedFile && `${(selectedFile.size / (1024 * 1024)).toLocaleString('en-US', { maximumFractionDigits: 1 })} MB`}</span></p>
                  <progress aria-label={`${item.label} upload progress`} value={progress.phase === 'uploading' && progress.percent !== null ? progress.percent : undefined} max={100} className="mt-3 h-2 w-full accent-emerald-500" />
                  <p role="status" className="mt-2 text-sm text-zinc-300">{progress.phase === 'preparing' ? 'Preparing secure upload…' : progress.phase === 'verifying' ? 'Transfer complete. Verifying the file…' : progress.percent === 100 ? '100% transferred. Waiting for storage confirmation…' : progress.percent === null ? 'Uploading… waiting for measurable transfer progress.' : `Uploading ${progress.percent}%…`}</p>
                  <p className="mt-1 text-xs text-zinc-500">Keep this page open. Your published commercial stays in place until you save a verified replacement.</p>
                </div>}
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
