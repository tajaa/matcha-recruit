import { useEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, X } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Card, ErrorText, Input, Select, Spinner, Textarea } from '../../components/ui'
import type { Brand, BrandPrompt } from '../../api/types'

const LOGO_MAX_BYTES = 2 * 1024 * 1024
const COVER_MAX_BYTES = 4 * 1024 * 1024

// Matches BRAND_HOURS_DAYS in server/app/tellus/models/tellus.py and
// HoursDisclosure.dayOrder in BrandDetailView.swift.
const HOURS_DAYS: { key: string; label: string }[] = [
  { key: 'mon', label: 'Mon' }, { key: 'tue', label: 'Tue' }, { key: 'wed', label: 'Wed' },
  { key: 'thu', label: 'Thu' }, { key: 'fri', label: 'Fri' }, { key: 'sat', label: 'Sat' },
  { key: 'sun', label: 'Sun' },
]

export default function BrandSettings() {
  const [brand, setBrand] = useState<Brand | null>(null)
  const [name, setName] = useState('')
  const [rewardMode, setRewardMode] = useState<'auto' | 'manual'>('auto')
  const [messagingEnabled, setMessagingEnabled] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [logoBusy, setLogoBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const [questions, setQuestions] = useState<string[]>([])
  const [qBusy, setQBusy] = useState(false)
  const [qMsg, setQMsg] = useState('')
  const [qErr, setQErr] = useState('')

  const [tagline, setTagline] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [website, setWebsite] = useState('')
  const [hours, setHours] = useState<Record<string, string>>({})
  const [categories, setCategories] = useState<string[]>([])
  const [profileBusy, setProfileBusy] = useState(false)
  const [profileMsg, setProfileMsg] = useState('')
  const [profileErr, setProfileErr] = useState('')
  const [coverBusy, setCoverBusy] = useState(false)
  const coverFileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    tellusApi.get<Brand>('/brand').then((b) => {
      setBrand(b); setName(b.name); setRewardMode(b.reward_mode); setMessagingEnabled(b.messaging_enabled ?? false)
      setTagline(b.tagline ?? ''); setDescription(b.description ?? ''); setCategory(b.category ?? '')
      setWebsite(b.website ?? ''); setHours(b.hours ?? {})
    })
    tellusApi.get<BrandPrompt[]>('/brand/prompts').then((ps) => setQuestions(ps.map((p) => p.prompt))).catch(() => {})
    tellusApi.get<string[]>('/brand/categories').then(setCategories).catch(() => {})
  }, [])

  async function uploadLogo(f: File) {
    if (f.size > LOGO_MAX_BYTES) { setErr('Logo must be 2MB or smaller.'); return }
    setLogoBusy(true); setErr(''); setMsg('')
    try {
      const form = new FormData()
      form.append('file', f)
      const b = await tellusApi.upload<Brand>('/brand/logo', form)
      setBrand(b); setMsg('Logo updated.')
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setLogoBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function removeLogo() {
    setLogoBusy(true); setErr(''); setMsg('')
    try {
      const b = await tellusApi.delete<Brand>('/brand/logo')
      setBrand(b); setMsg('Logo removed.')
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Remove failed')
    } finally {
      setLogoBusy(false)
    }
  }

  async function uploadCover(f: File) {
    if (f.size > COVER_MAX_BYTES) { setProfileErr('Cover must be 4MB or smaller.'); return }
    setCoverBusy(true); setProfileErr(''); setProfileMsg('')
    try {
      const form = new FormData()
      form.append('file', f)
      const b = await tellusApi.upload<Brand>('/brand/cover', form)
      setBrand(b); setProfileMsg('Cover updated.')
    } catch (e) {
      setProfileErr(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setCoverBusy(false)
      if (coverFileRef.current) coverFileRef.current.value = ''
    }
  }

  async function removeCover() {
    setCoverBusy(true); setProfileErr(''); setProfileMsg('')
    try {
      const b = await tellusApi.delete<Brand>('/brand/cover')
      setBrand(b); setProfileMsg('Cover removed.')
    } catch (e) {
      setProfileErr(e instanceof Error ? e.message : 'Remove failed')
    } finally {
      setCoverBusy(false)
    }
  }

  async function saveProfile() {
    setProfileBusy(true); setProfileErr(''); setProfileMsg('')
    try {
      const cleanedHours = Object.fromEntries(
        Object.entries(hours).filter(([, v]) => v.trim())
      )
      const b = await tellusApi.patch<Brand>('/brand', {
        tagline: tagline.trim() || null,
        description: description.trim() || null,
        category: category || null,
        website: website.trim() || null,
        hours: Object.keys(cleanedHours).length ? cleanedHours : null,
      })
      setBrand(b); setProfileMsg('Profile saved.')
    } catch (e) {
      setProfileErr(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setProfileBusy(false)
    }
  }

  function moveQuestion(i: number, dir: -1 | 1) {
    setQuestions((qs) => {
      const next = [...qs]
      const j = i + dir
      if (j < 0 || j >= next.length) return qs
      ;[next[i], next[j]] = [next[j], next[i]]
      return next
    })
  }

  async function saveQuestions() {
    setQBusy(true); setQErr(''); setQMsg('')
    try {
      const ps = await tellusApi.put<BrandPrompt[]>('/brand/prompts', {
        prompts: questions.filter((q) => q.trim()).map((q) => ({ prompt: q.trim() })),
      })
      setQuestions(ps.map((p) => p.prompt))
      setQMsg('Saved.')
    } catch (e) {
      setQErr(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setQBusy(false)
    }
  }

  async function save() {
    setBusy(true); setErr(''); setMsg('')
    try {
      const b = await tellusApi.patch<Brand>('/brand', { name, reward_mode: rewardMode })
      setBrand(b); setMsg('Saved.')
    } catch (e) { setErr(e instanceof Error ? e.message : 'Save failed') } finally { setBusy(false) }
  }

  async function toggleMessaging(enabled: boolean) {
    setBusy(true); setErr(''); setMsg('')
    try {
      await tellusApi.patch('/comms/brand/messaging', { enabled })
      setMessagingEnabled(enabled); setMsg(enabled ? 'Comms is now visible on your public page.' : 'Comms turned off.')
    } catch (e) { setErr(e instanceof Error ? e.message : 'Could not update Comms') }
    finally { setBusy(false) }
  }

  if (!brand) return <Spinner />

  return (
    <div className="max-w-lg space-y-5">
      <h1 className="text-lg font-bold">Brand settings</h1>
      <Card className="space-y-4">
        <Input label="Brand name" value={name} onChange={(e) => setName(e.target.value)} />
        <div>
          <p className="mb-1.5 text-sm font-medium text-tu-dim">Logo</p>
          <div className="flex items-center gap-3">
            {brand.logo_url ? (
              <img src={brand.logo_url} alt="" className="h-16 w-16 rounded-xl object-cover" />
            ) : (
              <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-tu-panel2 text-xs text-tu-faint">No logo</div>
            )}
            <div>
              <input
                ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void uploadLogo(f) }}
              />
              <Button variant="soft" size="sm" loading={logoBusy} onClick={() => fileRef.current?.click()}>
                Upload logo
              </Button>
              {brand.logo_url && (
                <Button variant="ghost" size="sm" loading={logoBusy} onClick={removeLogo} className="text-tu-bad">
                  Remove
                </Button>
              )}
              <p className="mt-1 text-xs text-tu-faint">PNG, JPEG, or WebP. Max 2MB.</p>
            </div>
          </div>
        </div>
        <Button onClick={save} loading={busy} variant="soft">Save</Button>
        {msg && <p className="text-sm text-tu-good">{msg}</p>}
        <ErrorText>{err}</ErrorText>
      </Card>

      <Card className="space-y-3">
        <h2 className="text-sm font-semibold">Comms</h2>
        <p className="text-xs text-tu-faint">Let customers ask your team questions that your website may not answer, such as holiday hours, reservations, or in-store inventory.</p>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={messagingEnabled} disabled={busy} onChange={e => void toggleMessaging(e.target.checked)} /> Accept Comms messages on my public page</label>
      </Card>

      <Card className="space-y-4">
        <h2 className="text-sm font-semibold">Public profile</h2>
        <p className="text-xs text-tu-faint">Shown on your unauthenticated business page and in Discover.</p>
        <Input label="Tagline" value={tagline} maxLength={120} onChange={(e) => setTagline(e.target.value)} />
        <Textarea label="About" value={description} maxLength={2000} rows={4} onChange={(e) => setDescription(e.target.value)} />
        <Select
          label="Category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          options={[{ value: '', label: '—' }, ...categories.map((c) => ({ value: c, label: c }))]}
        />
        <Input label="Website" value={website} placeholder="https://example.com" onChange={(e) => setWebsite(e.target.value)} />

        <div>
          <p className="mb-1.5 text-sm font-medium text-tu-dim">Cover image</p>
          <div className="flex items-center gap-3">
            {brand.cover_url ? (
              <img src={brand.cover_url} alt="" className="h-16 w-28 rounded-xl object-cover" />
            ) : (
              <div className="flex h-16 w-28 items-center justify-center rounded-xl bg-tu-panel2 text-xs text-tu-faint">No cover</div>
            )}
            <div>
              <input
                ref={coverFileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void uploadCover(f) }}
              />
              <Button variant="soft" size="sm" loading={coverBusy} onClick={() => coverFileRef.current?.click()}>
                Upload cover
              </Button>
              {brand.cover_url && (
                <Button variant="ghost" size="sm" loading={coverBusy} onClick={removeCover} className="text-tu-bad">
                  Remove
                </Button>
              )}
              <p className="mt-1 text-xs text-tu-faint">PNG, JPEG, or WebP. Max 4MB.</p>
            </div>
          </div>
        </div>

        <div>
          <p className="mb-1.5 text-sm font-medium text-tu-dim">Hours</p>
          <div className="space-y-1.5">
            {HOURS_DAYS.map(({ key, label }) => (
              <div key={key} className="flex items-center gap-2">
                <span className="w-10 text-xs text-tu-faint">{label}</span>
                <Input
                  value={hours[key] ?? ''}
                  placeholder="e.g. 9:00–17:00 or Closed"
                  maxLength={40}
                  onChange={(e) => setHours((h) => ({ ...h, [key]: e.target.value }))}
                />
              </div>
            ))}
          </div>
        </div>

        <Button onClick={saveProfile} loading={profileBusy} variant="soft">Save profile</Button>
        {profileMsg && <p className="text-sm text-tu-good">{profileMsg}</p>}
        <ErrorText>{profileErr}</ErrorText>
      </Card>

      <Card className="space-y-3">
        <h2 className="text-sm font-semibold">Reward approval</h2>
        <p className="text-xs text-tu-faint">How feedback earns points for your customers.</p>
        {([
          { value: 'auto', label: 'Automatic', desc: 'Useful feedback earns points immediately on submission.' },
          { value: 'manual', label: 'Manual review', desc: 'You approve or decline each submission before points are awarded.' },
        ] as const).map((opt) => (
          <label key={opt.value} className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition ${
            rewardMode === opt.value ? 'border-tu-accent bg-tu-accent/5' : 'border-tu-border'
          }`}>
            <input type="radio" name="reward_mode" className="mt-1 accent-tu-accent"
              checked={rewardMode === opt.value} onChange={() => setRewardMode(opt.value)} />
            <span>
              <span className="block text-sm font-semibold">{opt.label}</span>
              <span className="block text-xs text-tu-dim">{opt.desc}</span>
            </span>
          </label>
        ))}
        <Button onClick={save} loading={busy}>Save reward mode</Button>
      </Card>

      <Card className="space-y-3">
        <h2 className="text-sm font-semibold">Feedback questions</h2>
        <p className="text-xs text-tu-faint">Up to 5 custom questions shown on your intake form, in order.</p>
        {questions.map((q, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="flex-1">
              <Input
                value={q}
                onChange={(e) => setQuestions((qs) => qs.map((x, idx) => (idx === i ? e.target.value : x)))}
                placeholder="e.g. How was our service today?"
              />
            </div>
            <button type="button" onClick={() => moveQuestion(i, -1)} disabled={i === 0} className="text-tu-faint hover:text-tu-text disabled:opacity-30">
              <ArrowUp className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => moveQuestion(i, 1)} disabled={i === questions.length - 1} className="text-tu-faint hover:text-tu-text disabled:opacity-30">
              <ArrowDown className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => setQuestions((qs) => qs.filter((_, idx) => idx !== i))} className="text-tu-faint hover:text-tu-bad">
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
        <Button
          variant="soft" size="sm"
          disabled={questions.length >= 5}
          onClick={() => setQuestions((qs) => [...qs, ''])}
        >
          Add question
        </Button>
        <Button onClick={saveQuestions} loading={qBusy}>Save questions</Button>
        {qMsg && <p className="text-sm text-tu-good">{qMsg}</p>}
        <ErrorText>{qErr}</ErrorText>
      </Card>
    </div>
  )
}
