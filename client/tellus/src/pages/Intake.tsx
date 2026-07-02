import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Camera, CheckCircle2, Loader2, X } from 'lucide-react'
import { tellusMaybeAuthPost, tellusPublicGet, tellusPublicPost, getTellusToken } from '../api/tellusClient'
import { Button, Card, ErrorText, Input, Select, Spinner, Textarea } from '../components/ui'
import type { FeedbackSubmitResponse, IntakeConfig, MediaPresignResponse, SubmittedMedia } from '../api/types'

const SENTIMENTS = [
  { value: 'positive', label: '😊 Good', tone: 'text-tu-good border-tu-good/40 bg-tu-good/10' },
  { value: 'neutral', label: '😐 Okay', tone: 'text-tu-dim border-tu-border bg-tu-panel2' },
  { value: 'negative', label: '😞 Bad', tone: 'text-tu-bad border-tu-bad/40 bg-tu-bad/10' },
]

interface PendingMedia extends SubmittedMedia {
  name: string
  progress: number
  done: boolean
  error?: string
}

function uploadToS3(url: string, file: File, onProgress: (pct: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)
    xhr.setRequestHeader('Content-Type', file.type)
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100)) }
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`Upload failed (${xhr.status})`)))
    xhr.onerror = () => reject(new Error('Upload failed'))
    xhr.send(file)
  })
}

export default function Intake() {
  const { token = '' } = useParams()
  const [config, setConfig] = useState<IntakeConfig | null>(null)
  const [loadErr, setLoadErr] = useState('')
  const [loading, setLoading] = useState(true)

  const [category, setCategory] = useState('other')
  const [sentiment, setSentiment] = useState('neutral')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [contact, setContact] = useState('')
  const [website, setWebsite] = useState('') // honeypot
  const [media, setMedia] = useState<PendingMedia[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [result, setResult] = useState<FeedbackSubmitResponse | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const loggedIn = !!getTellusToken()

  useEffect(() => {
    tellusPublicGet<IntakeConfig>(`/i/${token}`)
      .then(setConfig)
      .catch((e) => setLoadErr(e instanceof Error ? e.message : 'This link is unavailable.'))
      .finally(() => setLoading(false))
  }, [token])

  async function onFiles(files: FileList | null) {
    if (!files) return
    for (const file of Array.from(files)) {
      const mediaType: 'photo' | 'video' = file.type.startsWith('video') ? 'video' : 'photo'
      const idx = media.length
      const entry: PendingMedia = {
        name: file.name, media_type: mediaType, mime_type: file.type,
        file_size: file.size, original_filename: file.name, storage_path: '', progress: 0, done: false,
      }
      setMedia((m) => [...m, entry])
      try {
        // Presign is a PUBLIC endpoint — use the unauthenticated helper, never
        // the authed client (whose 401-refresh failure hard-redirects to
        // /login, which would eject an anonymous reporter off this form).
        const presign = await tellusPublicPost<MediaPresignResponse>(`/i/${token}/media/presign`, {
          media_type: mediaType, mime_type: file.type, file_size: file.size, original_filename: file.name,
        })
        await uploadToS3(presign.upload_url, file, (pct) =>
          setMedia((m) => m.map((x, i) => (i === idx ? { ...x, progress: pct } : x))))
        setMedia((m) => m.map((x, i) => (i === idx ? { ...x, storage_path: presign.storage_path, done: true, progress: 100 } : x)))
      } catch (e) {
        setMedia((m) => m.map((x, i) => (i === idx ? { ...x, error: e instanceof Error ? e.message : 'Upload failed' } : x)))
      }
    }
    if (fileRef.current) fileRef.current.value = ''
  }

  function removeMedia(i: number) { setMedia((m) => m.filter((_, idx) => idx !== i)) }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(''); setBusy(true)
    try {
      const media_keys = media.filter((m) => m.done && m.storage_path).map((m) => ({
        storage_path: m.storage_path, media_type: m.media_type, mime_type: m.mime_type,
        file_size: m.file_size, original_filename: m.original_filename,
      }))
      const res = await tellusMaybeAuthPost<FeedbackSubmitResponse>(`/i/${token}`, {
        category, sentiment, title: title || null, description, reporter_contact: contact || null,
        media_keys, website,
      })
      setResult(res)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Submission failed')
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <div className="min-h-screen"><Spinner /></div>
  if (loadErr) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <h1 className="text-lg font-bold">Link unavailable</h1>
        <p className="mt-2 text-sm text-tu-dim">{loadErr}</p>
      </div>
    )
  }

  if (result) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <CheckCircle2 className="mx-auto mb-4 h-12 w-12 text-tu-good" />
        <h1 className="text-xl font-bold">Thanks for your feedback!</h1>
        {result.earned ? (
          <p className="mt-2 text-tu-accent">You earned +{result.points_awarded} points.</p>
        ) : result.reward_pending ? (
          <p className="mt-2 text-sm text-tu-dim">
            This brand reviews feedback before awarding points — you'll be notified once it's approved.
          </p>
        ) : loggedIn ? (
          <p className="mt-2 text-sm text-tu-dim">Your feedback was recorded.</p>
        ) : (
          <div className="mt-4">
            <p className="text-sm text-tu-dim">Sign in next time to earn points for useful feedback.</p>
            <Link to="/login" className="mt-3 inline-block font-semibold text-tu-accent hover:underline">Create a Tell-Us account →</Link>
          </div>
        )}
        {result.report_number && <p className="mt-4 text-xs text-tu-faint">Reference: {result.report_number}</p>}
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-md px-4 py-8">
      <div className="mb-6 text-center">
        {config?.brand_logo_url && <img src={config.brand_logo_url} alt="" className="mx-auto mb-3 h-12 w-12 rounded-xl object-cover" />}
        <h1 className="text-xl font-bold">{config?.brand_name}</h1>
        {config?.store_name && <p className="text-sm text-tu-dim">{config.store_name}</p>}
        <p className="mt-1 text-sm text-tu-faint">How was your experience?</p>
      </div>

      <Card>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-3 gap-2">
            {SENTIMENTS.map((s) => (
              <button key={s.value} type="button" onClick={() => setSentiment(s.value)}
                className={`rounded-lg border px-2 py-3 text-sm font-semibold transition ${sentiment === s.value ? s.tone : 'border-tu-border text-tu-dim'}`}>
                {s.label}
              </button>
            ))}
          </div>

          <Select label="Category" value={category} onChange={(e) => setCategory(e.target.value)}
            options={(config?.categories ?? []).map((c) => ({ value: c, label: c[0].toUpperCase() + c.slice(1) }))} />

          <Input label="Title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Short summary" />

          <Textarea label="Your feedback" required rows={5} value={description} onChange={(e) => setDescription(e.target.value)}
            placeholder="Tell them what happened — the more detail, the more useful (and the more points you earn)." />

          {/* Media */}
          <div>
            <span className="mb-1 block text-xs font-medium text-tu-dim">Photos / video (optional)</span>
            <button type="button" onClick={() => fileRef.current?.click()}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-tu-border py-3 text-sm text-tu-dim hover:border-tu-accent">
              <Camera className="h-4 w-4" /> Add photo or video
            </button>
            <input ref={fileRef} type="file" accept="image/*,video/*" multiple className="hidden" onChange={(e) => onFiles(e.target.files)} />
            {media.length > 0 && (
              <ul className="mt-2 space-y-1">
                {media.map((m, i) => (
                  <li key={i} className="flex items-center gap-2 rounded-lg bg-tu-panel2 px-3 py-2 text-xs">
                    <span className="flex-1 truncate">{m.name}</span>
                    {m.error ? <span className="text-tu-bad">{m.error}</span>
                      : m.done ? <CheckCircle2 className="h-4 w-4 text-tu-good" />
                      : <span className="flex items-center gap-1 text-tu-dim"><Loader2 className="h-3 w-3 animate-spin" />{m.progress}%</span>}
                    <button type="button" onClick={() => removeMedia(i)} className="text-tu-faint hover:text-tu-bad"><X className="h-3.5 w-3.5" /></button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {!loggedIn && (
            <Input label="Email (optional — to claim points later)" type="email" value={contact} onChange={(e) => setContact(e.target.value)} />
          )}

          {/* Honeypot — hidden from humans, bots fill it. */}
          <input type="text" value={website} onChange={(e) => setWebsite(e.target.value)} tabIndex={-1} autoComplete="off"
            className="hidden" aria-hidden="true" />

          <ErrorText>{err}</ErrorText>
          <Button type="submit" loading={busy} className="w-full" disabled={media.some((m) => !m.done && !m.error)}>
            Submit feedback
          </Button>
          {loggedIn ? (
            <p className="text-center text-xs text-tu-faint">Signed in — useful feedback earns points.</p>
          ) : (
            <p className="text-center text-xs text-tu-faint">
              <Link to="/login" className="text-tu-accent hover:underline">Sign in</Link> to earn points for this.
            </p>
          )}
        </form>
      </Card>
    </div>
  )
}
