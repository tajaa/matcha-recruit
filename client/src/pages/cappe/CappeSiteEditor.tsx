import { useEffect, useState } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { Loader2, ArrowLeft, Plus, Trash2, Rocket, Save, Globe } from 'lucide-react'
import { cappeApi } from '../../api/cappeClient'
import SiteTabs from '../../components/cappe/SiteTabs'
import type { CappePage, CappeSite } from '../../types/cappe'

const statusStyle: Record<string, string> = {
  published: 'bg-emerald-100 text-emerald-700',
  draft: 'bg-zinc-100 text-zinc-600',
  archived: 'bg-amber-100 text-amber-700',
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
  const [domain, setDomain] = useState('')
  const [saving, setSaving] = useState(false)
  const [publishing, setPublishing] = useState(false)
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
        setDomain(s.custom_domain || '')
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load site'))
      .finally(() => setLoading(false))
  }, [siteId])

  async function save() {
    if (!siteId) return
    setSaving(true)
    setError(null)
    try {
      const updated = await cappeApi.put<CappeSite>(`/sites/${siteId}`, {
        name,
        custom_domain: domain || null,
      })
      setSite(updated)
      setNotice('Saved.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
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

  async function addPage(e: React.FormEvent) {
    e.preventDefault()
    if (!siteId || !newPageTitle.trim()) return
    setAddingPage(true)
    try {
      const page = await cappeApi.post<CappePage>(`/sites/${siteId}/pages`, { title: newPageTitle.trim() })
      setPages((prev) => [...prev, page])
      setNewPageTitle('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add page')
    } finally {
      setAddingPage(false)
    }
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

  async function buy(kind: 'hosting' | 'domain') {
    if (!siteId) return
    setNotice(null)
    try {
      await cappeApi.post(`/sites/${siteId}/${kind === 'hosting' ? 'hosting/checkout' : 'domain/purchase'}`)
    } catch (e) {
      // 501 stub for now — surface as a friendly "coming soon".
      setNotice(`${kind === 'hosting' ? 'Hosting plans' : 'Domain purchase'} coming soon.`)
    }
  }

  async function deleteSite() {
    if (!siteId || !confirm('Delete this site and all its pages? This cannot be undone.')) return
    try {
      await cappeApi.delete(`/sites/${siteId}`)
      navigate('/cappe')
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
        <p className="text-sm text-red-600">{error || 'Site not found.'}</p>
        <Link to="/cappe" className="mt-4 inline-flex items-center gap-1 text-sm text-emerald-700 hover:underline">
          <ArrowLeft className="h-4 w-4" /> Back to sites
        </Link>
      </div>
    )
  }

  const publicUrl = site.custom_domain || `${site.subdomain || site.slug}.cappe.hey-matcha.com`

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <Link to="/cappe" className="mb-4 inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-800">
        <ArrowLeft className="h-4 w-4" /> My Sites
      </Link>

      <SiteTabs />

      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">{site.name}</h1>
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[site.status] || statusStyle.draft}`}>
              {site.status}
            </span>
          </div>
          <div className="mt-1 flex items-center gap-1 text-sm text-zinc-500">
            <Globe className="h-3.5 w-3.5" /> {publicUrl}
          </div>
        </div>
        <button
          onClick={publish}
          disabled={publishing}
          className="flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
        >
          {publishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
          {site.status === 'published' ? 'Re-publish' : 'Publish'}
        </button>
      </div>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}
      {notice && <p className="mb-4 text-sm text-emerald-700">{notice}</p>}

      {/* Settings */}
      <section className="mb-6 rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-sm font-semibold text-zinc-900">Site settings</h2>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-700">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-zinc-700">Custom domain (bring your own)</label>
            <input
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="www.yourdomain.com"
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
            />
            <p className="mt-1 text-xs text-zinc-400">
              Don't have one?{' '}
              <button onClick={() => buy('domain')} className="font-medium text-emerald-700 hover:underline">
                Buy a domain
              </button>{' '}
              or{' '}
              <button onClick={() => buy('hosting')} className="font-medium text-emerald-700 hover:underline">
                get a hosting plan
              </button>
              .
            </p>
          </div>
          <button
            onClick={save}
            disabled={saving}
            className="flex items-center gap-2 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-60"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save changes
          </button>
        </div>
      </section>

      {/* Pages */}
      <section className="mb-6 rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-sm font-semibold text-zinc-900">Pages</h2>
        <ul className="mb-4 divide-y divide-zinc-100">
          {pages.length === 0 && <li className="py-3 text-sm text-zinc-400">No pages yet.</li>}
          {pages.map((p) => (
            <li key={p.id} className="flex items-center justify-between py-3">
              <div>
                <div className="text-sm font-medium text-zinc-800">{p.title}</div>
                <div className="text-xs text-zinc-400">/{p.slug}</div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[p.status] || statusStyle.draft}`}>
                  {p.status}
                </span>
                <button onClick={() => deletePage(p.id)} className="text-zinc-400 hover:text-red-600">
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
            className="flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
          />
          <button
            type="submit"
            disabled={addingPage || !newPageTitle.trim()}
            className="flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
          >
            {addingPage ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Add
          </button>
        </form>
      </section>

      <button onClick={deleteSite} className="text-sm text-red-600 hover:underline">
        Delete site
      </button>
    </div>
  )
}
