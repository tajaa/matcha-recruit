import { useEffect, useState } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { Loader2, ArrowLeft, Plus, Trash2, Rocket, Save, Globe, Pencil, Check, Sparkles } from 'lucide-react'
import { cappeApi } from '../api'
import ImageUpload from '../components/ImageUpload'
import SetupGuide from '../components/SetupGuide'
import DomainManager from '../components/DomainManager'
import { cappeSiteHost, CAPPE_HOST } from '../host'
import { CAPPE_THEMES, type CappeThemePreset } from '../data/cappeThemes'
import { PAGE_PRESETS, type CappePagePreset } from '../data/cappePagePresets'
import { CAPPE_TIMEZONES } from '../data/timezones'
import type { CappePage, CappeSite } from '../types'

const statusStyle: Record<string, string> = {
  published: 'bg-emerald-500/15 text-emerald-400',
  draft: 'bg-zinc-800 text-zinc-400',
  archived: 'bg-amber-500/15 text-amber-400',
}

const inputCls =
  'w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500'

// ── business info + SEO, stored as meta_config keys ──────────────────────────
type Social = { instagram: string; x: string; tiktok: string; youtube: string; facebook: string; linkedin: string; website: string }
type DayHours = { day: number; open: string; close: string; closed: boolean }
type BizMeta = {
  contact_email: string; contact_phone: string; contact_address: string; business_hours: string
  favicon_url: string; social: Social; seo: { title: string; description: string; og_image: string }
  hours: DayHours[]; lat: string; lng: string
}
const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const defaultHours = (): DayHours[] =>
  DAY_LABELS.map((_, day) => ({ day, open: '09:00', close: '17:00', closed: day >= 5 }))
const SOCIAL_FIELDS: { key: keyof Social; label: string; ph: string }[] = [
  { key: 'instagram', label: 'Instagram', ph: 'https://instagram.com/you' },
  { key: 'x', label: 'X', ph: 'https://x.com/you' },
  { key: 'tiktok', label: 'TikTok', ph: 'https://tiktok.com/@you' },
  { key: 'youtube', label: 'YouTube', ph: 'https://youtube.com/@you' },
  { key: 'facebook', label: 'Facebook', ph: 'https://facebook.com/you' },
  { key: 'linkedin', label: 'LinkedIn', ph: 'https://linkedin.com/in/you' },
  { key: 'website', label: 'Other website', ph: 'https://yoursite.com' },
]
const gstr = (o: Record<string, unknown> | undefined, k: string): string =>
  (o && typeof o[k] === 'string' ? (o[k] as string) : '')
function bizFromMeta(m: Record<string, unknown> | undefined): BizMeta {
  const s = (m?.social ?? {}) as Record<string, unknown>
  const seo = (m?.seo ?? {}) as Record<string, unknown>
  const geo = (m?.geo ?? {}) as Record<string, unknown>
  const rawHours = Array.isArray(m?.hours) ? (m!.hours as DayHours[]) : []
  const hours = defaultHours().map((d) => {
    const found = rawHours.find((h) => Number(h?.day) === d.day)
    return found ? { day: d.day, open: found.open || '09:00', close: found.close || '17:00', closed: !!found.closed } : d
  })
  const numStr = (v: unknown) => (typeof v === 'number' ? String(v) : typeof v === 'string' ? v : '')
  return {
    contact_email: gstr(m, 'contact_email'), contact_phone: gstr(m, 'contact_phone'),
    contact_address: gstr(m, 'contact_address'), business_hours: gstr(m, 'business_hours'),
    favicon_url: gstr(m, 'favicon_url'),
    social: {
      instagram: gstr(s, 'instagram'), x: gstr(s, 'x'), tiktok: gstr(s, 'tiktok'), youtube: gstr(s, 'youtube'),
      facebook: gstr(s, 'facebook'), linkedin: gstr(s, 'linkedin'), website: gstr(s, 'website'),
    },
    seo: { title: gstr(seo, 'title'), description: gstr(seo, 'description'), og_image: gstr(seo, 'og_image') },
    hours, lat: numStr(geo.lat), lng: numStr(geo.lng),
  }
}
const orNull = (v: string) => v.trim() || null
function bizToMeta(b: BizMeta): Record<string, unknown> {
  const social: Record<string, string> = {}
  SOCIAL_FIELDS.forEach(({ key }) => { if (b.social[key].trim()) social[key] = b.social[key].trim() })
  // Persist hours only if at least one day is open; geo only if both numbers parse.
  const anyOpen = b.hours.some((h) => !h.closed)
  const lat = parseFloat(b.lat), lng = parseFloat(b.lng)
  const geo = !Number.isNaN(lat) && !Number.isNaN(lng) ? { lat, lng } : null
  return {
    contact_email: orNull(b.contact_email), contact_phone: orNull(b.contact_phone),
    contact_address: orNull(b.contact_address), business_hours: orNull(b.business_hours),
    favicon_url: orNull(b.favicon_url), social,
    seo: { title: orNull(b.seo.title), description: orNull(b.seo.description), og_image: orNull(b.seo.og_image) },
    hours: anyOpen ? b.hours.map((h) => ({ day: h.day, open: h.open, close: h.close, closed: h.closed })) : [],
    geo,
  }
}

export default function CappeSiteEditor() {
  const { siteId } = useParams<{ siteId: string }>()
  const navigate = useNavigate()
  const [site, setSite] = useState<CappeSite | null>(null)
  const [pages, setPages] = useState<CappePage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [subdomain, setSubdomain] = useState('')
  const [logo, setLogo] = useState('')
  const [timezone, setTimezone] = useState('UTC')
  const [biz, setBiz] = useState<BizMeta>(bizFromMeta(undefined))
  const [saving, setSaving] = useState(false)
  const [themeBusy, setThemeBusy] = useState<string | null>(null)
  const [publishing, setPublishing] = useState(false)
  const [setupRefresh, setSetupRefresh] = useState(0)
  const [newPageTitle, setNewPageTitle] = useState('')
  const [addingPage, setAddingPage] = useState(false)

  useEffect(() => {
    if (!siteId) return
    Promise.all([
      cappeApi.get<CappeSite>(`/sites/${siteId}`),
      cappeApi.get<CappePage[]>(`/sites/${siteId}/pages`),
    ])
      .then(([s, p]) => {
        setSite(s)
        setPages(p)
        setName(s.name)
        setSubdomain(s.subdomain || s.slug)
        setLogo((s.meta_config?.logo_url as string) || '')
        setTimezone(s.timezone || 'UTC')
        setBiz(bizFromMeta(s.meta_config))
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load site'))
      .finally(() => setLoading(false))
  }, [siteId])

  async function save() {
    if (!siteId) return
    setSaving(true)
    setError(null)
    try {
      const body: Record<string, unknown> = {
        name,
        timezone,
        meta_config: {
          ...(site?.meta_config || {}),
          logo_url: logo.trim() || null,
          ...bizToMeta(biz),
        },
      }
      // Only send subdomain when it actually changed (avoids a needless slug
      // churn + uniqueness check on every save).
      if (subdomain && subdomain !== (site?.subdomain || site?.slug)) body.subdomain = subdomain
      const updated = await cappeApi.put<CappeSite>(`/sites/${siteId}`, body)
      setSite(updated)
      setSubdomain(updated.subdomain || updated.slug)
      setSetupRefresh((n) => n + 1) // re-check the launch checklist after edits
      setNotice('Saved.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  async function applyTheme(preset: CappeThemePreset) {
    if (!siteId) return
    setThemeBusy(preset.id)
    setError(null)
    setNotice(null)
    try {
      const updated = await cappeApi.put<CappeSite>(`/sites/${siteId}`, {
        theme_config: { ...preset.config, preset: preset.id },
      })
      setSite(updated)
      setNotice(`Theme "${preset.name}" applied.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to apply theme')
    } finally {
      setThemeBusy(null)
    }
  }

  async function publish() {
    if (!siteId) return
    setPublishing(true)
    setError(null)
    try {
      const updated = await cappeApi.post<CappeSite>(`/sites/${siteId}/publish`)
      setSite(updated)
      setPages((prev) => prev.map((p) => (p.status === 'draft' ? { ...p, status: 'published' } : p)))
      setNotice('Site published.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to publish')
    } finally {
      setPublishing(false)
    }
  }

  async function createPage(title: string, content?: Record<string, unknown>) {
    if (!siteId || !title.trim()) return
    setAddingPage(true)
    try {
      const body: Record<string, unknown> = { title: title.trim() }
      if (content) body.content = content
      const page = await cappeApi.post<CappePage>(`/sites/${siteId}/pages`, body)
      setPages((prev) => [...prev, page])
      setNewPageTitle('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add page')
    } finally {
      setAddingPage(false)
    }
  }

  async function addPage(e: React.FormEvent) {
    e.preventDefault()
    await createPage(newPageTitle)
  }

  function addPreset(p: CappePagePreset) {
    if (addingPage) return
    createPage(p.title, { blocks: p.blocks })
  }

  async function deletePage(pageId: string) {
    if (!siteId) return
    try {
      await cappeApi.delete(`/sites/${siteId}/pages/${pageId}`)
      setPages((prev) => prev.filter((p) => p.id !== pageId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete page')
    }
  }

  async function deleteSite() {
    if (!siteId || !confirm('Delete this site and all its pages? This cannot be undone.')) return
    try {
      await cappeApi.delete(`/sites/${siteId}`)
      navigate('/cappe/sites')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete site')
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
      </div>
    )
  }

  if (!site) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-10">
        <p className="text-sm text-red-400">{error || 'Site not found.'}</p>
        <Link to="/cappe/sites" className="mt-4 inline-flex items-center gap-1 text-sm text-emerald-400 hover:text-emerald-300">
          <ArrowLeft className="h-4 w-4" /> Back to sites
        </Link>
      </div>
    )
  }

  const publicUrl = cappeSiteHost(site)

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">{site.name}</h1>
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[site.status] || statusStyle.draft}`}>
              {site.status}
            </span>
          </div>
          <div className="mt-1 flex items-center gap-1 text-sm text-zinc-500">
            <Globe className="h-3.5 w-3.5" />
            {site.status === 'published' ? (
              <a href={`https://${publicUrl}`} target="_blank" rel="noreferrer" className="hover:text-emerald-400">
                {publicUrl}
              </a>
            ) : (
              publicUrl
            )}
          </div>
        </div>
        <button
          onClick={publish}
          disabled={publishing}
          className="flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60"
        >
          {publishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
          {site.status === 'published' ? 'Re-publish' : 'Publish'}
        </button>
      </div>

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}
      {notice && <p className="mb-4 text-sm text-emerald-400">{notice}</p>}

      <SetupGuide site={site} pages={pages} publishing={publishing} onPublish={publish} refreshKey={setupRefresh} />

      {/* Settings */}
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
        <h2 className="mb-4 text-sm font-semibold text-zinc-100">Site settings</h2>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Web address</label>
            <div className="flex items-center rounded-lg border border-zinc-700 bg-zinc-950 focus-within:border-emerald-500">
              <input
                value={subdomain}
                onChange={(e) => setSubdomain(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))}
                placeholder="your-name"
                className="min-w-0 flex-1 rounded-l-lg bg-transparent px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none"
              />
              <span className="shrink-0 px-3 text-sm text-zinc-500">.{CAPPE_HOST}</span>
            </div>
            <p className="mt-1 text-xs text-zinc-500">This is your site's public URL. Save to apply.</p>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Timezone</label>
            <select value={timezone} onChange={(e) => setTimezone(e.target.value)} className={inputCls}>
              {CAPPE_TIMEZONES.map((tz) => <option key={tz.value} value={tz.value}>{tz.label}</option>)}
            </select>
            <p className="mt-1 text-xs text-zinc-500">Booking times show in this zone. Set it so customers see the right hours.</p>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Logo</label>
            <ImageUpload siteId={siteId || ''} value={logo} onChange={setLogo} placeholder="Logo image URL" />
            <p className="mt-1 text-xs text-zinc-500">Shown in your published site's header. Save to apply.</p>
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-zinc-300">Custom domain</label>
            <DomainManager siteId={siteId || ''} />
          </div>
          <button
            onClick={save}
            disabled={saving}
            className="flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-800 disabled:opacity-60"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save changes
          </button>
        </div>
      </section>

      {/* Business info, social, SEO */}
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
        <h2 className="mb-1 text-sm font-semibold text-zinc-100">Business info &amp; SEO</h2>
        <p className="mb-4 text-xs text-zinc-500">Shown in your site footer and used for search/social previews. All optional.</p>
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-300">Contact email</label>
              <input value={biz.contact_email} onChange={(e) => setBiz((b) => ({ ...b, contact_email: e.target.value }))} placeholder="hello@yourbusiness.com" className={inputCls} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-300">Contact phone</label>
              <input value={biz.contact_phone} onChange={(e) => setBiz((b) => ({ ...b, contact_phone: e.target.value }))} placeholder="+1 555 123 4567" className={inputCls} />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Address</label>
            <input value={biz.contact_address} onChange={(e) => setBiz((b) => ({ ...b, contact_address: e.target.value }))} placeholder="123 Main St, City, ST" className={inputCls} />
            <p className="mt-1 text-xs text-zinc-500">Used by the Map / “Find us” block (with a Get-directions button).</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-300">Latitude <span className="text-zinc-500">(optional — adds a map)</span></label>
              <input value={biz.lat} onChange={(e) => setBiz((b) => ({ ...b, lat: e.target.value }))} placeholder="37.7749" className={inputCls} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-300">Longitude</label>
              <input value={biz.lng} onChange={(e) => setBiz((b) => ({ ...b, lng: e.target.value }))} placeholder="-122.4194" className={inputCls} />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Opening hours</label>
            <p className="mb-2 text-xs text-zinc-500">Powers the Hours block + a live “Open now” badge + search engines. (The free-text line below is a fallback.)</p>
            <div className="space-y-1.5">
              {biz.hours.map((h, i) => (
                <div key={h.day} className="flex items-center gap-2">
                  <span className="w-10 text-xs text-zinc-400">{DAY_LABELS[h.day]}</span>
                  <label className="flex items-center gap-1 text-xs text-zinc-500">
                    <input type="checkbox" checked={!h.closed} onChange={(e) => setBiz((b) => ({ ...b, hours: b.hours.map((x, j) => (j === i ? { ...x, closed: !e.target.checked } : x)) }))} className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-900 text-emerald-500" /> Open
                  </label>
                  {!h.closed ? (
                    <>
                      <input type="time" value={h.open} onChange={(e) => setBiz((b) => ({ ...b, hours: b.hours.map((x, j) => (j === i ? { ...x, open: e.target.value } : x)) }))} className={`${inputCls} w-32`} />
                      <span className="text-zinc-500">–</span>
                      <input type="time" value={h.close} onChange={(e) => setBiz((b) => ({ ...b, hours: b.hours.map((x, j) => (j === i ? { ...x, close: e.target.value } : x)) }))} className={`${inputCls} w-32`} />
                    </>
                  ) : <span className="text-xs text-zinc-600">Closed</span>}
                </div>
              ))}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-300">Hours (free text — fallback)</label>
            <input value={biz.business_hours} onChange={(e) => setBiz((b) => ({ ...b, business_hours: e.target.value }))} placeholder="Mon–Fri 9am–5pm" className={inputCls} />
          </div>

          <div className="border-t border-zinc-800 pt-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">Social links</p>
            <div className="grid gap-3 sm:grid-cols-2">
              {SOCIAL_FIELDS.map(({ key, label, ph }) => (
                <div key={key}>
                  <label className="mb-1 block text-xs font-medium text-zinc-400">{label}</label>
                  <input
                    value={biz.social[key]}
                    onChange={(e) => setBiz((b) => ({ ...b, social: { ...b.social, [key]: e.target.value } }))}
                    placeholder={ph}
                    className={inputCls}
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="border-t border-zinc-800 pt-4 space-y-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Search &amp; social preview (SEO)</p>
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-300">Page title</label>
              <input value={biz.seo.title} onChange={(e) => setBiz((b) => ({ ...b, seo: { ...b.seo, title: e.target.value } }))} placeholder={site.name} className={inputCls} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-300">Description</label>
              <textarea value={biz.seo.description} onChange={(e) => setBiz((b) => ({ ...b, seo: { ...b.seo, description: e.target.value } }))} rows={2} placeholder="One or two sentences describing your business." className={inputCls} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-zinc-300">Share image</label>
              <ImageUpload siteId={siteId || ''} value={biz.seo.og_image} onChange={(v) => setBiz((b) => ({ ...b, seo: { ...b.seo, og_image: v } }))} placeholder="Image shown when shared (1200×630)" />
            </div>
          </div>

          <div className="border-t border-zinc-800 pt-4">
            <label className="mb-1 block text-sm font-medium text-zinc-300">Favicon</label>
            <ImageUpload siteId={siteId || ''} value={biz.favicon_url} onChange={(v) => setBiz((b) => ({ ...b, favicon_url: v }))} placeholder="Browser-tab icon (square)" />
          </div>

          <button
            onClick={save}
            disabled={saving}
            className="flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-800 disabled:opacity-60"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save changes
          </button>
        </div>
      </section>

      {/* Design / theme */}
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-100">Design</h2>
          <span className="text-xs text-zinc-500">Applies instantly · re-publish to push live</span>
        </div>
        <p className="mb-4 text-xs text-zinc-500">Pick a look. Premium themes use designer fonts &amp; palettes.</p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {CAPPE_THEMES.map((preset) => {
            const active = (site.theme_config?.preset as string) === preset.id
            const busy = themeBusy === preset.id
            return (
              <button
                key={preset.id}
                onClick={() => applyTheme(preset)}
                disabled={!!themeBusy}
                className={`group relative overflow-hidden rounded-xl border text-left transition disabled:opacity-60 ${
                  active ? 'border-emerald-500 ring-1 ring-emerald-500' : 'border-zinc-700 hover:border-zinc-500'
                }`}
              >
                {/* swatch preview */}
                <div className="flex h-16 items-center gap-2 px-3" style={{ background: preset.swatch.bg }}>
                  <div className="h-7 w-7 rounded-md" style={{ background: preset.swatch.brand }} />
                  <div className="flex-1 space-y-1">
                    <div className="h-2 w-3/4 rounded" style={{ background: preset.swatch.text, opacity: 0.85 }} />
                    <div className="h-2 w-1/2 rounded" style={{ background: preset.swatch.surface }} />
                  </div>
                </div>
                <div className="flex items-center justify-between gap-1 border-t border-zinc-800 bg-zinc-950 px-3 py-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1 text-xs font-semibold text-zinc-200">
                      {preset.name}
                      {preset.premium && (
                        <span className="inline-flex items-center gap-0.5 rounded bg-amber-500/15 px-1 py-0.5 text-[9px] font-bold uppercase text-amber-400">
                          <Sparkles className="h-2.5 w-2.5" /> Premium
                        </span>
                      )}
                    </div>
                    <div className="truncate text-[10px] text-zinc-500">{preset.font}</div>
                  </div>
                  {busy ? (
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin text-emerald-400" />
                  ) : active ? (
                    <Check className="h-4 w-4 shrink-0 text-emerald-400" />
                  ) : null}
                </div>
              </button>
            )
          })}
        </div>
      </section>

      {/* Pages */}
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
        <h2 className="mb-4 text-sm font-semibold text-zinc-100">Pages</h2>
        <ul className="mb-4 divide-y divide-zinc-800">
          {pages.length === 0 && <li className="py-3 text-sm text-zinc-500">No pages yet.</li>}
          {pages.map((p) => (
            <li key={p.id} className="flex items-center justify-between py-3">
              <Link to={`/cappe/sites/${siteId}/pages/${p.id}`} className="group flex-1">
                <div className="text-sm font-medium text-zinc-200 group-hover:text-emerald-400">{p.title}</div>
                <div className="text-xs text-zinc-500">/{p.slug}</div>
              </Link>
              <div className="flex items-center gap-3">
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[p.status] || statusStyle.draft}`}>
                  {p.status}
                </span>
                <Link
                  to={`/cappe/sites/${siteId}/pages/${p.id}`}
                  className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800"
                >
                  <Pencil className="h-3.5 w-3.5" /> Edit
                </Link>
                <button onClick={() => deletePage(p.id)} className="text-zinc-500 hover:text-red-400">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
        <form onSubmit={addPage} className="flex gap-2">
          <input
            value={newPageTitle}
            onChange={(e) => setNewPageTitle(e.target.value)}
            placeholder="New page title"
            className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
          />
          <button
            type="submit"
            disabled={addingPage || !newPageTitle.trim()}
            className="flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60"
          >
            {addingPage ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Add
          </button>
        </form>

        {/* One-click page presets — seed a ready-made, fully-editable page. */}
        <div className="mt-4 border-t border-zinc-800 pt-4">
          <p className="mb-2 text-xs font-medium text-zinc-400">Or start from a template</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {PAGE_PRESETS.map((p) => (
              <button
                key={p.id}
                onClick={() => addPreset(p)}
                disabled={addingPage}
                className="flex flex-col items-start rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2.5 text-left hover:border-emerald-500/60 hover:bg-zinc-900 disabled:opacity-60"
              >
                <span className="flex items-center gap-1.5 text-sm font-semibold text-zinc-200">
                  <Sparkles className="h-3.5 w-3.5 text-emerald-400" /> {p.label}
                </span>
                <span className="mt-0.5 text-xs text-zinc-500">{p.blurb}</span>
              </button>
            ))}
          </div>
        </div>
      </section>

      <button onClick={deleteSite} className="text-sm text-red-400 hover:text-red-300">
        Delete site
      </button>
    </div>
  )
}
