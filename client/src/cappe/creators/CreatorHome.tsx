import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2, Plus, Trash2, Upload } from 'lucide-react'
import { cappeApi } from '../api'
import { ui, badgeFor } from '../components/ui'
import StripeConnectCard from '../components/StripeConnectCard'
import {
  CREATOR_NICHES, DELIVERABLE_TYPES, SOCIAL_PLATFORMS, fmtCents,
  type CreatorPortfolioItem, type CreatorProfileMe, type CreatorRate, type CreatorSocial,
} from '../types'
import { creatorProfilePath } from './creatorPaths'

type EditableSocial = { platform: string; handle: string; url: string; follower_count: number | null; engagement_rate: number | null; sort_order: number; _audit?: CreatorSocial['audit_status'] }
type EditablePortfolio = { title: string; description: string | null; media_url: string | null; media_type: 'image' | 'video' | null; external_url: string | null; brand_name: string | null; metrics: Record<string, unknown>; sort_order: number }
type EditableRate = { deliverable_type: string; platform: string; price_cents: number; negotiable: boolean; notes: string | null; sort_order: number; _priceText?: string }

function ClaimForm({ onCreated }: { onCreated: () => void }) {
  const [handle, setHandle] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await cappeApi.post('/creators/me', { handle, display_name: displayName })
      onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not claim that handle')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-md px-6 py-16">
      <h1 className={ui.heading}>Claim your creator profile</h1>
      <p className={`${ui.subtitle} mt-1`}>Pick a handle — this is your Gummfit URL.</p>
      <form onSubmit={submit} className={`${ui.card} mt-6 space-y-4 p-5`}>
        <div>
          <label className={ui.label}>Handle</label>
          <input value={handle} onChange={(e) => setHandle(e.target.value.toLowerCase())} placeholder="yourhandle" required className={ui.input} />
        </div>
        <div>
          <label className={ui.label}>Display name</label>
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required className={ui.input} />
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button type="submit" disabled={submitting} className={`${ui.btnPrimary} w-full`}>
          {submitting && <Loader2 className="h-4 w-4 animate-spin" />} Claim handle
        </button>
      </form>
    </div>
  )
}

function StatusBanner({ profile, onSubmit, onTogglePublic }: {
  profile: CreatorProfileMe
  onSubmit: () => void
  onTogglePublic: (v: boolean) => void
}) {
  if (profile.status === 'draft') {
    return (
      <div className="mb-6 flex items-center justify-between rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 text-sm">
        <span className="text-zinc-300">Your profile is a draft — submit it for review to get listed.</span>
        <button onClick={onSubmit} className={ui.btnPrimary}>Submit for review</button>
      </div>
    )
  }
  if (profile.status === 'pending_review') {
    return (
      <div className="mb-6 rounded-lg border border-amber-500/30 bg-amber-500/[0.06] px-4 py-3 text-sm text-amber-200">
        In review — we'll email you.
      </div>
    )
  }
  if (profile.status === 'rejected') {
    return (
      <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/[0.06] px-4 py-3 text-sm text-red-200">
        <p>{profile.review_note || 'Your profile needs changes before it can go live.'}</p>
        <button onClick={onSubmit} className={`${ui.btnPrimary} mt-2`}>Edit and resubmit</button>
      </div>
    )
  }
  if (profile.status === 'suspended') {
    return (
      <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/[0.06] px-4 py-3 text-sm text-red-200">
        Your profile is suspended.{profile.review_note ? ` ${profile.review_note}` : ''}
      </div>
    )
  }
  return (
    <div className="mb-6 flex items-center justify-between rounded-lg border border-emerald-500/30 bg-emerald-500/[0.06] px-4 py-3 text-sm">
      <span className="text-emerald-300">
        Live on Gummfit — <Link to={creatorProfilePath(profile.handle)} className="underline">view your public profile</Link>
      </span>
      <label className="flex items-center gap-1.5 text-zinc-300">
        <input type="checkbox" checked={profile.open_to_offers} onChange={(e) => onTogglePublic(e.target.checked)} /> Open to offers
      </label>
    </div>
  )
}

export default function CreatorHome() {
  const [profile, setProfile] = useState<CreatorProfileMe | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [loading, setLoading] = useState(true)

  function load() {
    setLoading(true)
    cappeApi.get<CreatorProfileMe>('/creators/me')
      .then((p) => { setProfile(p); setNotFound(false) })
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  if (loading) return <div className="flex items-center justify-center py-24"><Loader2 className="h-6 w-6 animate-spin text-zinc-600" /></div>
  if (notFound || !profile) return <ClaimForm onCreated={load} />

  async function submitForReview() {
    try {
      await cappeApi.post('/creators/me/submit')
      load()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : 'Could not submit')
    }
  }

  async function togglePublic(v: boolean) {
    try {
      await cappeApi.patch('/creators/me', { open_to_offers: v })
      load()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : 'Could not update')
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <h1 className={ui.heading}>My profile</h1>
      <p className={`${ui.subtitle} mb-4`}>@{profile.handle}</p>

      <StatusBanner profile={profile} onSubmit={submitForReview} onTogglePublic={togglePublic} />

      <BasicsSection profile={profile} onSaved={load} />
      <SocialsSection socials={profile.socials} onSaved={load} />
      <PortfolioSection items={profile.portfolio} onSaved={load} />
      <RatesSection rates={profile.rates} onSaved={load} />

      <section className={`${ui.card} mt-5 p-5`}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Payouts</h2>
        <StripeConnectCard />
        <p className="text-xs text-zinc-500">Brands can only pay you after Stripe payouts are enabled.</p>
      </section>
    </div>
  )
}

function BasicsSection({ profile, onSaved }: { profile: CreatorProfileMe; onSaved: () => void }) {
  const [displayName, setDisplayName] = useState(profile.display_name)
  const [bio, setBio] = useState(profile.bio ?? '')
  const [location, setLocation] = useState(profile.location ?? '')
  const [niches, setNiches] = useState<string[]>(profile.niches)
  const [languages, setLanguages] = useState(profile.languages.join(', '))
  const [avatarUrl, setAvatarUrl] = useState(profile.avatar_url)
  const [coverUrl, setCoverUrl] = useState(profile.cover_url)
  const [saving, setSaving] = useState(false)
  const avatarInput = useRef<HTMLInputElement>(null)
  const coverInput = useRef<HTMLInputElement>(null)

  async function upload(file: File): Promise<string> {
    const fd = new FormData()
    fd.append('file', file)
    const res = await cappeApi.upload<{ url: string }>('/creators/me/upload', fd)
    return res.url
  }

  function toggleNiche(n: string) {
    setNiches((prev) => (prev.includes(n) ? prev.filter((x) => x !== n) : prev.length < 6 ? [...prev, n] : prev))
  }

  async function save() {
    setSaving(true)
    try {
      await cappeApi.patch('/creators/me', {
        display_name: displayName,
        bio: bio || null,
        location: location || null,
        niches,
        languages: languages.split(',').map((s) => s.trim()).filter(Boolean),
        avatar_url: avatarUrl,
        cover_url: coverUrl,
      })
      onSaved()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className={`${ui.card} mb-5 p-5`}>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Basics</h2>
      <div className="mb-4 flex items-center gap-4">
        <div className="h-16 w-16 overflow-hidden rounded-full bg-zinc-800">
          {avatarUrl && <img src={avatarUrl} alt="" className="h-full w-full object-cover" />}
        </div>
        <button onClick={() => avatarInput.current?.click()} className={ui.btnGhost}>
          <Upload className="h-4 w-4" /> Avatar
        </button>
        <input ref={avatarInput} type="file" accept="image/*" hidden onChange={async (e) => { const f = e.target.files?.[0]; if (f) setAvatarUrl(await upload(f)) }} />
        <button onClick={() => coverInput.current?.click()} className={ui.btnGhost}>
          <Upload className="h-4 w-4" /> Cover
        </button>
        <input ref={coverInput} type="file" accept="image/*" hidden onChange={async (e) => { const f = e.target.files?.[0]; if (f) setCoverUrl(await upload(f)) }} />
      </div>
      <div className="space-y-3">
        <div>
          <label className={ui.label}>Display name</label>
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} className={ui.input} />
        </div>
        <div>
          <label className={ui.label}>Bio</label>
          <textarea value={bio} onChange={(e) => setBio(e.target.value)} rows={3} className={ui.input} />
        </div>
        <div>
          <label className={ui.label}>Location</label>
          <input value={location} onChange={(e) => setLocation(e.target.value)} className={ui.input} />
        </div>
        <div>
          <label className={ui.label}>Niches (up to 6)</label>
          <div className="flex flex-wrap gap-1.5">
            {CREATOR_NICHES.map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => toggleNiche(n)}
                className={`rounded-full border px-2.5 py-1 text-xs ${niches.includes(n) ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300' : 'border-zinc-700 text-zinc-400'}`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className={ui.label}>Languages (comma-separated)</label>
          <input value={languages} onChange={(e) => setLanguages(e.target.value)} className={ui.input} />
        </div>
        <button onClick={save} disabled={saving} className={ui.btnPrimary}>
          {saving && <Loader2 className="h-4 w-4 animate-spin" />} Save
        </button>
      </div>
    </section>
  )
}

function SocialsSection({ socials, onSaved }: { socials: CreatorSocial[]; onSaved: () => void }) {
  const [rows, setRows] = useState<EditableSocial[]>(
    socials.map((s) => ({ platform: s.platform, handle: s.handle, url: s.url, follower_count: s.follower_count, engagement_rate: s.engagement_rate, sort_order: s.sort_order, _audit: s.audit_status })),
  )
  const [saving, setSaving] = useState(false)
  const dirty = socials.length > 0 // editing any row resets verification — always warn if there's existing audit state

  function update(i: number, patch: Partial<EditableSocial>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }

  async function save() {
    setSaving(true)
    try {
      await cappeApi.put('/creators/me/socials', rows.map(({ _audit: _unused, ...r }) => r))
      onSaved()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className={`${ui.card} mb-5 p-5`}>
      <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-zinc-500">Socials</h2>
      {dirty && <p className="mb-3 text-xs text-amber-400">Editing resets verification on any changed row.</p>}
      <div className="space-y-2">
        {rows.map((s, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg border border-zinc-800 p-2">
            <select value={s.platform} onChange={(e) => update(i, { platform: e.target.value })} className={`${ui.input} w-auto`}>
              {SOCIAL_PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <input value={s.handle} onChange={(e) => update(i, { handle: e.target.value })} placeholder="handle" className={`${ui.input} w-28`} />
            <input value={s.url} onChange={(e) => update(i, { url: e.target.value })} placeholder="https://…" className={`${ui.input} flex-1`} />
            <input type="number" value={s.follower_count ?? ''} onChange={(e) => update(i, { follower_count: e.target.value ? Number(e.target.value) : null })} placeholder="followers" className={`${ui.input} w-24`} />
            {s._audit && <span className={badgeFor(s._audit)}>{s._audit}</span>}
            <button onClick={() => setRows((prev) => prev.filter((_, idx) => idx !== i))} className="text-zinc-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <button onClick={() => setRows((prev) => [...prev, { platform: 'instagram', handle: '', url: '', follower_count: null, engagement_rate: null, sort_order: prev.length }])} className={ui.btnGhost}>
          <Plus className="h-4 w-4" /> Add social
        </button>
        <button onClick={save} disabled={saving} className={ui.btnPrimary}>
          {saving && <Loader2 className="h-4 w-4 animate-spin" />} Save
        </button>
      </div>
    </section>
  )
}

function PortfolioSection({ items, onSaved }: { items: CreatorPortfolioItem[]; onSaved: () => void }) {
  const [rows, setRows] = useState<EditablePortfolio[]>(
    items.map((p) => ({ title: p.title, description: p.description, media_url: p.media_url, media_type: p.media_type, external_url: p.external_url, brand_name: p.brand_name, metrics: p.metrics, sort_order: p.sort_order })),
  )
  const [saving, setSaving] = useState(false)

  function update(i: number, patch: Partial<EditablePortfolio>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }

  async function uploadMedia(i: number, file: File) {
    const fd = new FormData()
    fd.append('file', file)
    const res = await cappeApi.upload<{ url: string }>('/creators/me/upload', fd)
    update(i, { media_url: res.url, media_type: file.type.startsWith('video') ? 'video' : 'image' })
  }

  async function save() {
    setSaving(true)
    try {
      await cappeApi.put('/creators/me/portfolio', rows)
      onSaved()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className={`${ui.card} mb-5 p-5`}>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Portfolio</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {rows.map((p, i) => (
          <div key={i} className="rounded-lg border border-zinc-800 p-3">
            <input value={p.title} onChange={(e) => update(i, { title: e.target.value })} placeholder="Title" className={`${ui.input} mb-2`} />
            <input value={p.brand_name ?? ''} onChange={(e) => update(i, { brand_name: e.target.value || null })} placeholder="Brand name" className={`${ui.input} mb-2`} />
            <textarea value={p.description ?? ''} onChange={(e) => update(i, { description: e.target.value || null })} placeholder="Description" rows={2} className={`${ui.input} mb-2`} />
            <input value={p.external_url ?? ''} onChange={(e) => update(i, { external_url: e.target.value || null })} placeholder="External URL (or upload media)" className={`${ui.input} mb-2`} />
            <label className={`${ui.btnGhost} w-full cursor-pointer justify-center`}>
              <Upload className="h-4 w-4" /> {p.media_url ? 'Replace media' : 'Upload media'}
              <input type="file" accept="image/*,video/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadMedia(i, f) }} />
            </label>
            <button onClick={() => setRows((prev) => prev.filter((_, idx) => idx !== i))} className={`${ui.danger} mt-2 text-xs`}>Remove</button>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <button onClick={() => setRows((prev) => [...prev, { title: '', description: null, media_url: null, media_type: null, external_url: null, brand_name: null, metrics: {}, sort_order: prev.length }])} className={ui.btnGhost}>
          <Plus className="h-4 w-4" /> Add item
        </button>
        <button onClick={save} disabled={saving} className={ui.btnPrimary}>
          {saving && <Loader2 className="h-4 w-4 animate-spin" />} Save
        </button>
      </div>
    </section>
  )
}

function RatesSection({ rates, onSaved }: { rates: CreatorRate[]; onSaved: () => void }) {
  const [rows, setRows] = useState<EditableRate[]>(
    rates.map((r) => ({
      deliverable_type: r.deliverable_type, platform: r.platform, price_cents: r.price_cents,
      negotiable: r.negotiable, notes: r.notes, sort_order: r.sort_order,
      _priceText: (r.price_cents / 100).toString(),
    })),
  )
  const [saving, setSaving] = useState(false)

  function update(i: number, patch: Partial<EditableRate>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }

  async function save() {
    setSaving(true)
    try {
      await cappeApi.put('/creators/me/rates', rows.map(({ _priceText: _unused, ...r }) => r))
      onSaved()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className={`${ui.card} mb-5 p-5`}>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Rates</h2>
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg border border-zinc-800 p-2">
            <select value={r.deliverable_type} onChange={(e) => update(i, { deliverable_type: e.target.value })} className={`${ui.input} w-auto`}>
              {DELIVERABLE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <select value={r.platform} onChange={(e) => update(i, { platform: e.target.value })} className={`${ui.input} w-auto`}>
              {SOCIAL_PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <input
              type="number" min={0} step="0.01"
              value={r._priceText ?? (r.price_cents / 100).toString()}
              onChange={(e) => {
                const text = e.target.value
                const n = Number(text)
                // Keep the raw text as-is (don't reformat on every keystroke)
                // so a trailing "." while typing "12.50" isn't snapped back
                // to "12" by the controlled value — only price_cents (the
                // field actually saved) is derived, and only when parseable.
                update(i, { _priceText: text, ...(text !== '' && !Number.isNaN(n) ? { price_cents: Math.round(n * 100) } : {}) })
              }}
              onBlur={() => update(i, { _priceText: (r.price_cents / 100).toString() })}
              className={`${ui.input} w-24`}
            />
            <span className="text-xs text-zinc-500">{fmtCents(r.price_cents)}</span>
            <label className="flex items-center gap-1 text-xs text-zinc-400">
              <input type="checkbox" checked={r.negotiable} onChange={(e) => update(i, { negotiable: e.target.checked })} /> negotiable
            </label>
            <button onClick={() => setRows((prev) => prev.filter((_, idx) => idx !== i))} className="ml-auto text-zinc-500 hover:text-red-400"><Trash2 className="h-4 w-4" /></button>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <button onClick={() => setRows((prev) => [...prev, { deliverable_type: 'post', platform: 'instagram', price_cents: 0, negotiable: true, notes: null, sort_order: prev.length, _priceText: '0' }])} className={ui.btnGhost}>
          <Plus className="h-4 w-4" /> Add rate
        </button>
        <button onClick={save} disabled={saving} className={ui.btnPrimary}>
          {saving && <Loader2 className="h-4 w-4 animate-spin" />} Save
        </button>
      </div>
    </section>
  )
}
