import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Check, Copy, Rocket, Loader2, Sparkles, ArrowRight, CircleAlert } from 'lucide-react'
import { cappeApi } from '../../api/cappeClient'
import { cappeSiteHost } from '../../utils/cappeHost'
import type { CappePage, CappeReadiness, CappeSite } from '../../types/cappe'

interface SetupGuideProps {
  site: CappeSite
  pages: CappePage[]
  publishing: boolean
  onPublish: () => void
  // bumped by the parent after edits/saves so the checklist re-checks
  refreshKey?: number
}

/** Launch checklist. Reads server readiness (the same gate the publish endpoint
 *  enforces), shows required vs. recommended steps with a deep link to build
 *  each, and only enables publish once the required items are done. */
export default function SetupGuide({ site, pages, publishing, onPublish, refreshKey }: SetupGuideProps) {
  const navigate = useNavigate()
  const [readiness, setReadiness] = useState<CappeReadiness | null>(null)
  const [copied, setCopied] = useState(false)
  const [creatingPage, setCreatingPage] = useState(false)

  const load = useCallback(() => {
    cappeApi.get<CappeReadiness>(`/sites/${site.id}/readiness`).then(setReadiness).catch(() => {})
  }, [site.id])

  useEffect(() => { load() }, [load, refreshKey, site.status])

  const host = cappeSiteHost(site)
  const url = `https://${host}`
  const homePageId = pages[0]?.id

  // Map a readiness action to a destination in the dashboard.
  function actionTo(action: string | null): string {
    switch (action) {
      case 'shop': return `/cappe/sites/${site.id}/shop`
      case 'pages': return homePageId ? `/cappe/sites/${site.id}/pages/${homePageId}` : `/cappe/sites/${site.id}`
      case 'settings': return `/cappe/sites/${site.id}`
      default: return `/cappe/sites/${site.id}`
    }
  }

  // Page-editing tasks (intro/about, sell-on-page, contact) need a page to open.
  // Blank sites historically shipped with none, so the 'pages' deep link
  // resolved to the dashboard the user was already on — a dead "Do this".
  // Create a Home page on the fly, then open the editor.
  async function goToPageAction() {
    if (homePageId) { navigate(actionTo('pages')); return }
    if (creatingPage) return
    setCreatingPage(true)
    try {
      const page = await cappeApi.post<CappePage>(`/sites/${site.id}/pages`, { title: 'Home' })
      navigate(`/cappe/sites/${site.id}/pages/${page.id}`)
    } catch {
      navigate(`/cappe/sites/${site.id}`)
    } finally {
      setCreatingPage(false)
    }
  }

  // Published + ready → collapse to a compact "live" card with the share link.
  if (site.status === 'published') {
    return (
      <section className="mb-6 rounded-2xl border border-emerald-500/25 bg-emerald-500/[0.05] p-5">
        <div className="flex flex-wrap items-center gap-3">
          <Rocket className="h-5 w-5 text-emerald-400" />
          <div className="flex-1">
            <div className="text-sm font-semibold text-zinc-100">Your site is live</div>
            <a href={url} target="_blank" rel="noreferrer" className="text-xs text-emerald-400 hover:underline">{host}</a>
          </div>
          <button
            onClick={() => { navigator.clipboard.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) }) }}
            className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-300 hover:bg-zinc-800"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? 'Copied' : 'Copy link'}
          </button>
        </div>
      </section>
    )
  }

  if (!readiness) {
    return (
      <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
        <Loader2 className="h-5 w-5 animate-spin text-zinc-500" />
      </section>
    )
  }

  const required = readiness.items.filter((i) => i.required)
  const recommended = readiness.items.filter((i) => !i.required)
  const requiredDone = required.filter((i) => i.done).length

  const Row = ({ item }: { item: CappeReadiness['items'][number] }) => (
    <li className="flex items-start gap-3">
      <span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
        item.done ? 'bg-emerald-500 text-zinc-950' : 'border border-zinc-700 text-zinc-500'
      }`}>
        {item.done ? <Check className="h-3 w-3" /> : ''}
      </span>
      <div className="min-w-0 flex-1">
        <div className={`text-sm font-medium ${item.done ? 'text-zinc-500 line-through' : 'text-zinc-200'}`}>
          {item.label}
        </div>
        {!item.done && (
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="text-xs leading-relaxed text-zinc-400">{item.hint}</span>
            {item.action === 'pages' && !homePageId ? (
              <button
                onClick={goToPageAction}
                disabled={creatingPage}
                className="inline-flex items-center gap-1 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-60"
              >
                Do this {creatingPage ? <Loader2 className="h-3 w-3 animate-spin" /> : <ArrowRight className="h-3 w-3" />}
              </button>
            ) : (
              <Link to={actionTo(item.action)} className="inline-flex items-center gap-1 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20">
                Do this <ArrowRight className="h-3 w-3" />
              </Link>
            )}
          </div>
        )}
      </div>
    </li>
  )

  return (
    <section className="mb-6 rounded-2xl border border-emerald-500/25 bg-emerald-500/[0.04] p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <Sparkles className="h-4 w-4 text-emerald-400" /> Get your site ready to launch
        </h2>
        <span className="text-xs text-zinc-500">{requiredDone} of {required.length} required done</span>
      </div>

      <ul className="space-y-4">
        {required.map((i) => <Row key={i.key} item={i} />)}
      </ul>

      {recommended.length > 0 && (
        <>
          <div className="mb-3 mt-6 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Recommended</div>
          <ul className="space-y-4">
            {recommended.map((i) => <Row key={i.key} item={i} />)}
          </ul>
        </>
      )}

      <div className="mt-6 flex items-center gap-3 border-t border-zinc-800 pt-4">
        <button
          onClick={onPublish}
          disabled={publishing || !readiness.ready}
          title={readiness.ready ? 'Publish your site' : 'Finish the required steps first'}
          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {publishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
          Publish site
        </button>
        {!readiness.ready && (
          <span className="inline-flex items-center gap-1 text-xs text-amber-400">
            <CircleAlert className="h-3.5 w-3.5" /> Finish the required steps to publish
          </span>
        )}
      </div>
    </section>
  )
}
