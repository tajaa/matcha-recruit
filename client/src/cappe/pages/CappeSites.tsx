import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2, Plus, Globe, FileText, ExternalLink, Check } from 'lucide-react'
import { cappeApi } from '../api'
import { cappeSiteHost, CAPPE_HOST } from '../host'
import type { CappeSite } from '../types'

const statusStyle: Record<string, string> = {
  published: 'bg-emerald-500/15 text-emerald-400',
  draft: 'bg-zinc-800 text-zinc-400',
  archived: 'bg-amber-500/15 text-amber-400',
}

export default function CappeSites() {
  const navigate = useNavigate()
  const [sites, setSites] = useState<CappeSite[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [naming, setNaming] = useState(false)
  const [siteName, setSiteName] = useState('')
  const [creatingBlank, setCreatingBlank] = useState(false)

  useEffect(() => {
    cappeApi
      .get<CappeSite[]>('/sites')
      .then((list) => {
        // First run (no sites yet) → the business-setup wizard, not a bare empty state.
        if (list.length === 0) {
          navigate('/cappe/onboarding', { replace: true })
          return
        }
        setSites(list)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load sites'))
  }, [navigate])

  async function createBlank() {
    if (!siteName.trim()) return
    setCreatingBlank(true)
    setError(null)
    try {
      const site = await cappeApi.post<CappeSite>('/sites', { name: siteName.trim(), source_type: 'blank' })
      navigate(`/cappe/sites/${site.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create site')
      setCreatingBlank(false)
      setNaming(false)
    }
  }

  const slugPreview = siteName.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'your-name'

  return (
    <div className="mx-auto max-w-5xl px-8 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">My Sites</h1>
          <p className="mt-1 text-sm text-zinc-400">Create, edit, and publish your websites.</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => { setSiteName(''); setNaming(true) }}
            className="flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-800"
          >
            <Plus className="h-4 w-4" />
            Blank site
          </button>
          <Link
            to="/cappe/templates"
            className="flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400"
          >
            <Plus className="h-4 w-4" />
            Start from template
          </Link>
        </div>
      </div>

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      {sites === null ? (
        <div className="flex justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
        </div>
      ) : sites.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-700 bg-zinc-900 py-16 text-center">
          <Globe className="mx-auto mb-3 h-8 w-8 text-zinc-600" />
          <p className="text-sm text-zinc-400">No sites yet. Start from a template to get going fast.</p>
          <Link
            to="/cappe/templates"
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400"
          >
            Browse templates
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {sites.map((site) => (
            <Link
              key={site.id}
              to={`/cappe/sites/${site.id}`}
              className="group rounded-2xl border border-zinc-800 bg-zinc-900 p-5 transition hover:border-zinc-700"
            >
              <div className="mb-3 flex items-start justify-between">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-zinc-800 text-zinc-400 group-hover:bg-emerald-500/10 group-hover:text-emerald-400">
                  <Globe className="h-4 w-4" />
                </span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[site.status] || statusStyle.draft}`}>
                  {site.status}
                </span>
              </div>
              <h3 className="truncate font-medium text-zinc-100">{site.name}</h3>
              <div className="mt-1 flex items-center gap-1 text-xs text-zinc-500">
                <ExternalLink className="h-3 w-3" />
                <span className="truncate">{cappeSiteHost(site)}</span>
              </div>
              <div className="mt-3 flex items-center gap-1 text-xs text-zinc-500">
                <FileText className="h-3 w-3" />
                {site.page_count ?? 0} page{(site.page_count ?? 0) === 1 ? '' : 's'}
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Name-your-site modal (blank create) — the name seeds the subdomain. */}
      {naming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4" onClick={() => !creatingBlank && setNaming(false)}>
          <form
            onClick={(e) => e.stopPropagation()}
            onSubmit={(e) => { e.preventDefault(); createBlank() }}
            className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900 p-6"
          >
            <h2 className="text-lg font-semibold text-zinc-50">Name your site</h2>
            <p className="mt-1 text-sm text-zinc-400">Usually your business or your own name — it becomes your web address.</p>
            <input
              autoFocus
              value={siteName}
              onChange={(e) => setSiteName(e.target.value)}
              placeholder="e.g. Avery Lane Pilates"
              maxLength={255}
              className="mt-4 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
            />
            <p className="mt-2 min-h-[1rem] text-xs text-zinc-500">
              {siteName.trim() && <>Your site: <span className="text-emerald-400">{slugPreview}.{CAPPE_HOST}</span></>}
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setNaming(false)} disabled={creatingBlank} className="rounded-lg border border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">Cancel</button>
              <button type="submit" disabled={!siteName.trim() || creatingBlank} className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
                {creatingBlank ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                Create site
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
