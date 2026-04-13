import { useEffect, useState } from 'react'
import { Loader2, Plus, Trash2, Upload, Check } from 'lucide-react'
import { Card, Button } from '../../components/ui'
import { landingMedia, type LandingMedia, type LandingSizzleVideo, type LandingCustomerLogo, type LandingTestimonial } from '../../api/client'

const EMPTY: LandingMedia = {
  hero_video_url: null,
  hero_poster_url: null,
  sizzle_videos: [],
  customer_logos: [],
  testimonials: [],
}

export default function LandingMediaAdmin() {
  const [data, setData] = useState<LandingMedia>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    landingMedia.getAdmin()
      .then((res) => setData({ ...EMPTY, ...res }))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  async function uploadFile(file: File, kind: 'video' | 'image', slot: string) {
    setUploading(slot)
    setError(null)
    try {
      const res = await landingMedia.upload(file, kind)
      return res.url
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
      return null
    } finally {
      setUploading(null)
    }
  }

  async function handleHeroVideo(file: File) {
    const url = await uploadFile(file, 'video', 'hero_video')
    if (url) setData({ ...data, hero_video_url: url })
  }

  async function handleHeroPoster(file: File) {
    const url = await uploadFile(file, 'image', 'hero_poster')
    if (url) setData({ ...data, hero_poster_url: url })
  }

  async function handleSizzleVideo(idx: number, file: File) {
    const url = await uploadFile(file, 'video', `sizzle_${idx}`)
    if (!url) return
    const next = [...data.sizzle_videos]
    next[idx] = { ...next[idx], url }
    setData({ ...data, sizzle_videos: next })
  }

  async function handleLogoUpload(idx: number, file: File) {
    const url = await uploadFile(file, 'image', `logo_${idx}`)
    if (!url) return
    const next = [...data.customer_logos]
    next[idx] = { ...next[idx], url }
    setData({ ...data, customer_logos: next })
  }

  function addSizzle() {
    setData({
      ...data,
      sizzle_videos: [
        ...data.sizzle_videos,
        { id: `sizzle-${Date.now()}`, title: 'New section', caption: '', url: null },
      ],
    })
  }
  function removeSizzle(idx: number) {
    setData({ ...data, sizzle_videos: data.sizzle_videos.filter((_, i) => i !== idx) })
  }
  function updateSizzle(idx: number, patch: Partial<LandingSizzleVideo>) {
    const next = [...data.sizzle_videos]
    next[idx] = { ...next[idx], ...patch }
    setData({ ...data, sizzle_videos: next })
  }

  function addLogo() {
    setData({ ...data, customer_logos: [...data.customer_logos, { name: '', url: '' }] })
  }
  function removeLogo(idx: number) {
    setData({ ...data, customer_logos: data.customer_logos.filter((_, i) => i !== idx) })
  }
  function updateLogo(idx: number, patch: Partial<LandingCustomerLogo>) {
    const next = [...data.customer_logos]
    next[idx] = { ...next[idx], ...patch }
    setData({ ...data, customer_logos: next })
  }

  function addTestimonial() {
    setData({
      ...data,
      testimonials: [...data.testimonials, { quote: '', author: '', title: '' }],
    })
  }
  function removeTestimonial(idx: number) {
    setData({ ...data, testimonials: data.testimonials.filter((_, i) => i !== idx) })
  }
  function updateTestimonial(idx: number, patch: Partial<LandingTestimonial>) {
    const next = [...data.testimonials]
    next[idx] = { ...next[idx], ...patch }
    setData({ ...data, testimonials: next })
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      await landingMedia.save(data)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center gap-2 text-zinc-400">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading…
      </div>
    )
  }

  return (
    <div className="p-6 max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Landing Page Media</h1>
          <p className="text-sm text-zinc-500">Hero video, product walkthroughs, customer logos, and testimonials for the public landing page.</p>
        </div>
        <div className="flex items-center gap-3">
          {saved && <span className="text-xs text-emerald-400 flex items-center gap-1"><Check className="w-3.5 h-3.5" /> Saved</span>}
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save All'}
          </Button>
        </div>
      </div>

      {error && <div className="p-3 rounded border border-red-900/40 bg-red-950/20 text-sm text-red-300">{error}</div>}

      {/* Hero */}
      <Card>
        <div className="p-5 space-y-4">
          <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wide">Hero</h2>
          <p className="text-xs text-zinc-500">
            Headline and subcopy are managed in code. Upload a cinematic video here to replace the default
            animated GRC dashboard in the hero. Poster image is shown while the video loads.
          </p>

          <Field label="Hero Video (mp4/mov/webm, max 25MB — compress with HandBrake first)">
            <MediaUploader
              currentUrl={data.hero_video_url}
              kind="video"
              uploading={uploading === 'hero_video'}
              onSelect={handleHeroVideo}
              onClear={() => setData({ ...data, hero_video_url: null })}
            />
          </Field>

          <Field label="Hero Poster Image (shown while video loads)">
            <MediaUploader
              currentUrl={data.hero_poster_url}
              kind="image"
              uploading={uploading === 'hero_poster'}
              onSelect={handleHeroPoster}
              onClear={() => setData({ ...data, hero_poster_url: null })}
            />
          </Field>
        </div>
      </Card>

      {/* Sizzle videos */}
      <Card>
        <div className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wide">Product Walkthroughs</h2>
            <Button onClick={addSizzle}><Plus className="w-4 h-4" /> Add</Button>
          </div>

          {data.sizzle_videos.length === 0 && (
            <p className="text-sm text-zinc-500">No walkthroughs yet. The landing page will show default placeholders until you add some.</p>
          )}

          <div className="space-y-4">
            {data.sizzle_videos.map((s, i) => (
              <div key={i} className="border border-zinc-800 rounded p-4 space-y-3 relative">
                <button onClick={() => removeSizzle(i)} className="absolute top-3 right-3 text-zinc-500 hover:text-red-400">
                  <Trash2 className="w-4 h-4" />
                </button>
                <Field label="Title">
                  <input
                    className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100"
                    value={s.title}
                    onChange={(e) => updateSizzle(i, { title: e.target.value })}
                  />
                </Field>
                <Field label="Caption">
                  <input
                    className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100"
                    value={s.caption ?? ''}
                    onChange={(e) => updateSizzle(i, { caption: e.target.value })}
                  />
                </Field>
                <Field label="Video">
                  <MediaUploader
                    currentUrl={s.url}
                    kind="video"
                    uploading={uploading === `sizzle_${i}`}
                    onSelect={(f) => handleSizzleVideo(i, f)}
                    onClear={() => updateSizzle(i, { url: null })}
                  />
                </Field>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Customer logos */}
      <Card>
        <div className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wide">Customer Logos</h2>
            <Button onClick={addLogo}><Plus className="w-4 h-4" /> Add</Button>
          </div>
          {data.customer_logos.length === 0 && (
            <p className="text-sm text-zinc-500">No customer logos yet.</p>
          )}
          <div className="space-y-3">
            {data.customer_logos.map((l, i) => (
              <div key={i} className="flex items-center gap-3">
                <input
                  className="flex-1 bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100"
                  placeholder="Company name"
                  value={l.name}
                  onChange={(e) => updateLogo(i, { name: e.target.value })}
                />
                <div className="flex-1">
                  <MediaUploader
                    currentUrl={l.url || null}
                    kind="image"
                    uploading={uploading === `logo_${i}`}
                    onSelect={(f) => handleLogoUpload(i, f)}
                    onClear={() => updateLogo(i, { url: '' })}
                  />
                </div>
                <button onClick={() => removeLogo(i)} className="text-zinc-500 hover:text-red-400">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Testimonials */}
      <Card>
        <div className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wide">Testimonials</h2>
            <Button onClick={addTestimonial}><Plus className="w-4 h-4" /> Add</Button>
          </div>
          {data.testimonials.length === 0 && (
            <p className="text-sm text-zinc-500">No testimonials yet.</p>
          )}
          <div className="space-y-4">
            {data.testimonials.map((t, i) => (
              <div key={i} className="border border-zinc-800 rounded p-4 space-y-3 relative">
                <button onClick={() => removeTestimonial(i)} className="absolute top-3 right-3 text-zinc-500 hover:text-red-400">
                  <Trash2 className="w-4 h-4" />
                </button>
                <Field label="Quote">
                  <textarea
                    className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100"
                    rows={2}
                    value={t.quote}
                    onChange={(e) => updateTestimonial(i, { quote: e.target.value })}
                  />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Author">
                    <input
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100"
                      value={t.author}
                      onChange={(e) => updateTestimonial(i, { author: e.target.value })}
                    />
                  </Field>
                  <Field label="Title / Company">
                    <input
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100"
                      value={t.title}
                      onChange={(e) => updateTestimonial(i, { title: e.target.value })}
                    />
                  </Field>
                </div>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs text-zinc-500 uppercase tracking-wide">{label}</span>
      <div className="mt-1.5">{children}</div>
    </label>
  )
}

function MediaUploader({
  currentUrl,
  kind,
  uploading,
  onSelect,
  onClear,
}: {
  currentUrl: string | null
  kind: 'video' | 'image'
  uploading: boolean
  onSelect: (f: File) => void
  onClear: () => void
}) {
  const accept = kind === 'video' ? 'video/mp4,video/quicktime,video/webm' : 'image/*'
  return (
    <div className="flex items-center gap-3">
      {currentUrl ? (
        kind === 'video' ? (
          <video src={currentUrl} className="w-32 h-20 rounded object-cover bg-zinc-900" muted />
        ) : (
          <img src={currentUrl} className="w-32 h-20 rounded object-contain bg-zinc-900" alt="" />
        )
      ) : (
        <div className="w-32 h-20 rounded bg-zinc-900 border border-dashed border-zinc-700 flex items-center justify-center text-xs text-zinc-600">
          None
        </div>
      )}
      <label className="inline-flex items-center gap-2 px-3 py-2 rounded bg-zinc-800 hover:bg-zinc-700 text-sm cursor-pointer text-zinc-100">
        {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
        <span>{currentUrl ? 'Replace' : 'Upload'}</span>
        <input
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) onSelect(f)
            e.target.value = ''
          }}
        />
      </label>
      {currentUrl && (
        <button onClick={onClear} className="text-xs text-zinc-500 hover:text-red-400">Clear</button>
      )}
    </div>
  )
}
