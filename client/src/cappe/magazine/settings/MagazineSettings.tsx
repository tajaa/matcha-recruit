import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { cappeApi } from '../../api'
import SurfaceShell from '../../components/SurfaceShell'
import { ui } from '../../components/ui'
import type { CappeMagazine, CappeStoryOptions } from '../../types'

const MASTHEADS: { key: CappeMagazine['masthead_style']; label: string; note: string }[] = [
  { key: 'classic', label: 'Classic', note: 'Bodoni Moda with Spectral — the fashion-magazine look.' },
  { key: 'literary', label: 'Literary', note: 'Newsreader throughout — long reads.' },
  { key: 'modern', label: 'Modern', note: 'Archivo Black with Libre Franklin — loud and square.' },
  { key: 'elegant', label: 'Elegant', note: 'Cormorant with EB Garamond — light and airy.' },
  { key: 'display', label: 'Display', note: 'Playfair Display with Lora — the Sunday supplement.' },
]

type Form = Pick<CappeMagazine, 'enabled' | 'name' | 'tagline' | 'about' | 'masthead_style' | 'accent' | 'topics' | 'front_at_root' | 'nav_label' | 'follow_enabled'>

const pick = (m: CappeMagazine): Form => ({
  enabled: m.enabled, name: m.name, tagline: m.tagline, about: m.about, masthead_style: m.masthead_style,
  accent: m.accent, topics: m.topics, front_at_root: m.front_at_root, nav_label: m.nav_label, follow_enabled: m.follow_enabled,
})

/** `sites/:siteId/magazine` — the magazine's name and masthead, its topics,
 *  whether it is on, and whether it is the site's front page. */
export default function MagazineSettings() {
  const { siteId } = useParams<{ siteId: string }>()
  const [magazine, setMagazine] = useState<CappeMagazine | null>(null)
  const [form, setForm] = useState<Form | null>(null)
  const [topics, setTopics] = useState<{ key: string; label: string }[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      cappeApi.get<CappeMagazine>(`/sites/${siteId}/magazine`),
      cappeApi.get<CappeStoryOptions>(`/sites/${siteId}/stories/options`),
    ]).then(([m, o]) => {
      if (cancelled) return
      setMagazine(m)
      setForm(pick(m))
      setTopics(o.topics)
    }).catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load the magazine') })
    return () => { cancelled = true }
  }, [siteId])

  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((f) => (f ? { ...f, [key]: value } : f))
    setSaved(false)
  }

  const toggleTopic = (key: string) => {
    if (!form) return
    const has = form.topics.includes(key)
    if (!has && form.topics.length >= 5) return
    set('topics', has ? form.topics.filter((t) => t !== key) : [...form.topics, key])
  }

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form) return
    setSaving(true)
    setError(null)
    try {
      const next = await cappeApi.put<CappeMagazine>(`/sites/${siteId}/magazine`, {
        ...form, name: form.name.trim(), nav_label: form.nav_label.trim() || 'Magazine',
        tagline: form.tagline?.trim() || null, about: form.about?.trim() || null, accent: form.accent || null,
      })
      setMagazine(next)
      setForm(pick(next))
      setSaved(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <SurfaceShell
      title="Magazine settings"
      subtitle="The masthead, the topics, and whether the magazine is on."
      actions={<Link to={`/cappe/sites/${siteId}/stories`} className={ui.btnGhost}><ArrowLeft className="h-4 w-4" /> Stories</Link>}
    >
      {error && <p role="alert" className="mb-4 text-sm text-red-400">{error}</p>}
      {!form && !error && <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div>}
      {form && magazine && (
        <form onSubmit={save} className="space-y-6">
          {!magazine.plan_includes_magazine && (
            <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              Your plan doesn’t include a magazine. You can write and lay out stories now; they go live on a Writer, Creator, Business or Pro plan.
            </p>
          )}
          <section className={`${ui.card} space-y-4 p-5`}>
            <label className="flex items-start gap-3 text-sm text-zinc-200">
              <input type="checkbox" checked={form.enabled} onChange={(e) => set('enabled', e.target.checked)} className="mt-0.5" />
              <span>
                <span className="font-medium">Magazine on</span>
                <span className="block text-xs text-zinc-500">
                  {magazine.live ? 'Live: your stories render on your site.' : 'Off: the magazine pages answer 404 and nothing links to them.'}
                </span>
              </span>
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label>
                <span className={ui.label}>Name</span>
                <input value={form.name} onChange={(e) => set('name', e.target.value)} maxLength={120} required className={ui.input} />
              </label>
              <label>
                <span className={ui.label}>Tagline</span>
                <input value={form.tagline || ''} onChange={(e) => set('tagline', e.target.value)} maxLength={200} className={ui.input}
                  placeholder="Stories from the harbour" />
              </label>
            </div>
            <label>
              <span className={ui.label}>About (Markdown, shown under the front page)</span>
              <textarea value={form.about || ''} onChange={(e) => set('about', e.target.value)} maxLength={4000} rows={3} className={ui.input} />
            </label>
          </section>

          <section className={`${ui.card} space-y-4 p-5`}>
            <h2 className="text-sm font-medium text-zinc-100">Masthead</h2>
            <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Masthead style">
              {MASTHEADS.map((m) => (
                <label key={m.key} className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm ${form.masthead_style === m.key ? 'border-emerald-500 bg-emerald-500/5' : 'border-zinc-800 hover:border-zinc-600'}`}>
                  <input type="radio" name="masthead" value={m.key} checked={form.masthead_style === m.key}
                    onChange={() => set('masthead_style', m.key)} className="mt-0.5" />
                  <span><span className="font-medium text-zinc-100">{m.label}</span><span className="block text-xs text-zinc-500">{m.note}</span></span>
                </label>
              ))}
            </div>
            <label className="flex items-center gap-3 text-sm text-zinc-200">
              <span className={`${ui.label} mb-0`}>Accent</span>
              <input type="color" value={form.accent || '#a3e635'} onChange={(e) => set('accent', e.target.value)} aria-label="Accent colour" />
              {form.accent && <button type="button" className="text-xs text-zinc-500 hover:text-zinc-300" onClick={() => set('accent', null)}>Use the site’s</button>}
            </label>
          </section>

          <section className={`${ui.card} space-y-3 p-5`}>
            <h2 className="text-sm font-medium text-zinc-100">Topics <span className="text-xs text-zinc-500">(up to 5, shown under the masthead)</span></h2>
            <div className="flex flex-wrap gap-2">
              {topics.map((t) => {
                const on = form.topics.includes(t.key)
                return (
                  <button key={t.key} type="button" aria-pressed={on} onClick={() => toggleTopic(t.key)}
                    className={`rounded-full border px-3 py-1 text-xs ${on ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300' : 'border-zinc-700 text-zinc-400 hover:border-zinc-500'}`}>
                    {t.label}
                  </button>
                )
              })}
            </div>
          </section>

          <section className={`${ui.card} space-y-4 p-5`}>
            <h2 className="text-sm font-medium text-zinc-100">Where it lives</h2>
            <label className="flex items-start gap-3 text-sm text-zinc-200">
              <input type="checkbox" checked={form.front_at_root} onChange={(e) => set('front_at_root', e.target.checked)} className="mt-0.5" />
              <span><span className="font-medium">The magazine is the home page</span>
                <span className="block text-xs text-zinc-500">Your site’s address opens the magazine’s front. Your pages stay at /p/…</span></span>
            </label>
            {!form.front_at_root && (
              <label className="block max-w-xs">
                <span className={ui.label}>Link in the site’s menu</span>
                <input value={form.nav_label} onChange={(e) => set('nav_label', e.target.value)} maxLength={40} className={ui.input} />
              </label>
            )}
            <label className="flex items-start gap-3 text-sm text-zinc-200">
              <input type="checkbox" checked={form.follow_enabled} onChange={(e) => set('follow_enabled', e.target.checked)} className="mt-0.5" />
              <span><span className="font-medium">Readers can follow</span>
                <span className="block text-xs text-zinc-500">A follow form on the magazine pages (email issues arrive in a later release).</span></span>
            </label>
          </section>

          <div className="flex items-center gap-3">
            <button type="submit" disabled={saving || !form.name.trim()} className={ui.btnPrimary}>
              {saving && <Loader2 className="h-4 w-4 animate-spin" />} Save
            </button>
            {saved && <span className="text-sm text-emerald-400">Saved.</span>}
          </div>
        </form>
      )}
    </SurfaceShell>
  )
}
