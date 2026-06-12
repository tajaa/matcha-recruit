import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2, Plus, Globe, FileText, ExternalLink } from 'lucide-react'
import { cappeApi } from '../../api/cappeClient'
import type { CappeSite } from '../../types/cappe'

const statusStyle: Record<string, string> = {
  published: 'bg-emerald-100 text-emerald-700',
  draft: 'bg-zinc-100 text-zinc-600',
  archived: 'bg-amber-100 text-amber-700',
}

export default function CappeSites() {
  const navigate = useNavigate()
  const [sites, setSites] = useState<CappeSite[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creatingBlank, setCreatingBlank] = useState(false)

  useEffect(() => {
    cappeApi
      .get<CappeSite[]>('/sites')
      .then(setSites)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load sites'))
  }, [])

  async function createBlank() {
    setCreatingBlank(true)
    try {
      const site = await cappeApi.post<CappeSite>('/sites', { name: 'Untitled site', source_type: 'blank' })
      navigate(`/cappe/sites/${site.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create site')
      setCreatingBlank(false)
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-8 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">My Sites</h1>
          <p className="mt-1 text-sm text-zinc-500">Create, edit, and publish your websites.</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={createBlank}
            disabled={creatingBlank}
            className="flex items-center gap-2 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-60"
          >
            {creatingBlank ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Blank site
          </button>
          <Link
            to="/cappe/templates"
            className="flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700"
          >
            <Plus className="h-4 w-4" />
            Start from template
          </Link>
        </div>
      </div>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {sites === null ? (
        <div className="flex justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-zinc-400" />
        </div>
      ) : sites.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-300 bg-white py-16 text-center">
          <Globe className="mx-auto mb-3 h-8 w-8 text-zinc-300" />
          <p className="text-sm text-zinc-500">No sites yet. Start from a template to get going fast.</p>
          <Link
            to="/cappe/templates"
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700"
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
              className="group rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md"
            >
              <div className="mb-3 flex items-start justify-between">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-zinc-100 text-zinc-500 group-hover:bg-emerald-50 group-hover:text-emerald-600">
                  <Globe className="h-4 w-4" />
                </span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[site.status] || statusStyle.draft}`}>
                  {site.status}
                </span>
              </div>
              <h3 className="truncate font-medium text-zinc-900">{site.name}</h3>
              <div className="mt-1 flex items-center gap-1 text-xs text-zinc-500">
                <ExternalLink className="h-3 w-3" />
                <span className="truncate">{site.custom_domain || `${site.subdomain || site.slug}.cappe.hey-matcha.com`}</span>
              </div>
              <div className="mt-3 flex items-center gap-1 text-xs text-zinc-400">
                <FileText className="h-3 w-3" />
                {site.page_count ?? 0} page{(site.page_count ?? 0) === 1 ? '' : 's'}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
