import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Check } from 'lucide-react'
import { CappeApiError, cappeApi } from '../api'
import UpgradeNotice from '../components/UpgradeNotice'
import TemplateGallery from '../components/TemplateGallery'
import { useCappeMe } from '../hooks/useCappeMe'
import { CAPPE_HOST } from '../host'
import { subdomainPreview } from '../utils/slug'
import type { CappeSite, CappeTemplateSummary } from '../types'

export default function CappeTemplates() {
  const navigate = useNavigate()
  const { account } = useCappeMe()
  const [error, setError] = useState<string | null>(null)
  const [limitHit, setLimitHit] = useState(false)
  const [usingId, setUsingId] = useState<string | null>(null)
  // Template picked but site not yet named — drives the naming modal. The
  // site name seeds the subdomain (slug), so we always ask instead of
  // silently naming the site after the template.
  const [naming, setNaming] = useState<CappeTemplateSummary | null>(null)
  const [siteName, setSiteName] = useState('')

  async function createFromTemplate(t: CappeTemplateSummary, name: string) {
    setUsingId(t.id)
    setError(null)
    setLimitHit(false)
    try {
      const site = await cappeApi.post<CappeSite>('/sites/from-template', {
        template_id: t.id,
        name,
      })
      navigate(`/cappe/sites/${site.id}`)
    } catch (e) {
      setLimitHit(e instanceof CappeApiError && e.code === 'site_limit_reached')
      setError(e instanceof Error ? e.message : 'Failed to create site')
      setUsingId(null)
      setNaming(null)
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-8 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">Templates</h1>
        <p className="mt-1 text-sm text-zinc-400">Pick a design — we'll clone it into a new site you can edit.</p>
      </div>

      {error && (limitHit
        ? <UpgradeNotice message={error} />
        : <p role="alert" className="mb-4 text-sm text-red-400">{error}</p>)}

      <TemplateGallery
        accountType={account?.account_type}
        busyId={usingId}
        onPick={(t) => { setSiteName(''); setNaming(t) }}
      />

      {/* Name-your-site modal — the name seeds the public subdomain. */}
      {naming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4" onClick={() => usingId === null && setNaming(null)}>
          <form
            onClick={(e) => e.stopPropagation()}
            onSubmit={(e) => {
              e.preventDefault()
              if (siteName.trim()) createFromTemplate(naming, siteName.trim())
            }}
            className="w-full max-w-md rounded-2xl border border-zinc-800 bg-zinc-900 p-6"
          >
            <h2 className="text-lg font-semibold text-zinc-50">Name your site</h2>
            <p className="mt-1 text-sm text-zinc-400">
              Usually your business or your own name — it becomes your web address.
            </p>
            <input
              autoFocus
              value={siteName}
              onChange={(e) => setSiteName(e.target.value)}
              placeholder="e.g. Avery Lane Pilates"
              maxLength={255}
              className="mt-4 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
            />
            <p className="mt-2 min-h-[1rem] text-xs text-zinc-500">
              {siteName.trim() && (
                <>Your site: <span className="text-emerald-400">{subdomainPreview(siteName)}.{CAPPE_HOST}</span></>
              )}
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" onClick={() => setNaming(null)} disabled={usingId !== null}
                className="rounded-lg border border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60">
                Cancel
              </button>
              <button type="submit" disabled={!siteName.trim() || usingId !== null}
                className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
                {usingId !== null ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                Create site
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
