import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowRight, Check, ExternalLink, ImagePlus, Loader2, Plus, Rocket } from 'lucide-react'
import { cappeApi } from '../api'
import { cappeSiteHost } from '../host'
import { formatCents } from '../pages/landing/shared'
import { readinessActionPath } from '../utils/readinessAction'
import type { CappePage, CappeProduct, CappeReadiness, CappeSite } from '../types'

// Where the wizard's quick store lands (/cappe/sites/:siteId/ready): the
// product on sale, one tap to publish, and the rest as optional next steps.
// Nothing here is required reading: no checklist wall, no settings form.

// Checklist items this page already answers by showing the store.
const SHOWN_HERE = new Set(['content', 'offering', 'sell_on_page'])

export default function StoreReady() {
  const { siteId = '' } = useParams()
  const [site, setSite] = useState<CappeSite | null>(null)
  const [products, setProducts] = useState<CappeProduct[]>([])
  const [readiness, setReadiness] = useState<CappeReadiness | null>(null)
  const [homePageId, setHomePageId] = useState<string | undefined>()
  const [loadError, setLoadError] = useState<string | null>(null)
  const [publishing, setPublishing] = useState(false)
  const [publishError, setPublishError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    Promise.all([
      cappeApi.get<CappeSite>(`/sites/${siteId}`),
      cappeApi.get<CappeProduct[]>(`/sites/${siteId}/products`),
      cappeApi.get<CappeReadiness>(`/sites/${siteId}/readiness`),
      cappeApi.get<CappePage[]>(`/sites/${siteId}/pages`).catch(() => [] as CappePage[]),
    ])
      .then(([s, p, r, pages]) => {
        if (!alive) return
        setSite(s)
        setProducts(p.filter((x) => x.status === 'active'))
        setReadiness(r)
        setHomePageId(pages[0]?.id)
      })
      .catch((e) => { if (alive) setLoadError(e instanceof Error ? e.message : 'Could not load your store.') })
    return () => { alive = false }
  }, [siteId])

  async function publish() {
    if (publishing) return
    setPublishing(true)
    setPublishError(null)
    try {
      setSite(await cappeApi.post<CappeSite>(`/sites/${siteId}/publish`))
    } catch (e) {
      setPublishError(e instanceof Error ? e.message : 'Could not publish. Try again.')
    } finally {
      setPublishing(false)
    }
  }

  if (loadError) {
    return (
      <div className="flex min-h-full items-center justify-center bg-zinc-950 px-4">
        <p role="alert" className="text-sm text-red-400">{loadError}</p>
      </div>
    )
  }
  if (!site || !readiness) {
    return (
      <div className="flex min-h-full items-center justify-center bg-zinc-950">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
      </div>
    )
  }

  const host = cappeSiteHost(site)
  const live = site.status === 'published'
  const next = readiness.items.filter((i) => !i.required && !i.done && !SHOWN_HERE.has(i.key))
  const shop = `/cappe/sites/${site.id}/shop`

  return (
    <div className="min-h-full bg-zinc-950 bg-[radial-gradient(60rem_40rem_at_50%_-10%,rgba(198,241,107,0.08),transparent)] px-4 py-10">
      <div className="mx-auto w-full max-w-2xl">
        <div className="mb-8 text-center">
          <span className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-lime-400 text-zinc-950 shadow-lg shadow-lime-500/20">
            <Check className="h-6 w-6" />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">
            {live ? `${site.name} is live` : `${site.name} is ready to sell`}
          </h1>
          <p className="mt-1 text-sm text-zinc-400">
            {live ? (
              <>Anyone can shop at <a href={`https://${host}`} target="_blank" rel="noreferrer" className="text-lime-400 hover:text-lime-300">{host}</a></>
            ) : (
              <>Publish it and it's live at <span className="text-lime-400">{host}</span>. You can change everything later.</>
            )}
          </p>
        </div>

        <section className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-xl shadow-black/40">
          <h2 className="mb-3 text-sm font-semibold text-zinc-200">On sale</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {products.map((p) => (
              <div key={p.id} className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950">
                {p.image_url ? (
                  <img src={p.image_url} alt="" className="aspect-square w-full object-cover" />
                ) : (
                  <Link to={shop} className="flex aspect-square w-full flex-col items-center justify-center gap-1 text-xs text-zinc-500 hover:text-zinc-300">
                    <ImagePlus className="h-5 w-5" /> Add a photo
                  </Link>
                )}
                <div className="p-3">
                  <p className="truncate text-sm font-medium text-zinc-100">{p.name}</p>
                  <p className="text-sm text-zinc-400">{formatCents(p.price_cents, p.currency)}</p>
                </div>
              </div>
            ))}
            <Link
              to={shop}
              className="flex aspect-square flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-zinc-700 text-sm text-zinc-400 hover:border-lime-400 hover:text-lime-300"
            >
              <Plus className="h-5 w-5" />
              {products.length ? 'Add another product' : 'Add your first product'}
            </Link>
          </div>

          <div className="mt-5 border-t border-zinc-800 pt-5">
            {live ? (
              <a
                href={`https://${host}`}
                target="_blank"
                rel="noreferrer"
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-lime-400 px-4 py-2.5 text-sm font-semibold text-zinc-950 hover:bg-lime-300"
              >
                View your store <ExternalLink className="h-4 w-4" />
              </a>
            ) : (
              <button
                type="button"
                onClick={publish}
                disabled={publishing}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-lime-400 px-4 py-2.5 text-sm font-semibold text-zinc-950 hover:bg-lime-300 disabled:opacity-60"
              >
                {publishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
                Publish my store
              </button>
            )}
            {publishError && <p role="alert" className="mt-2 text-sm text-red-400">{publishError}</p>}
          </div>
        </section>

        <section className="mt-6">
          <h2 className="mb-2 px-1 text-xs font-medium uppercase tracking-wide text-zinc-500">When you're ready</h2>
          <ul className="divide-y divide-zinc-800 rounded-2xl border border-zinc-800 bg-zinc-900">
            <NextStep
              to={readinessActionPath(site.id, 'policies')}
              label="Read your return and shipping policies"
              hint="We started them from our standard text so you could publish. Make them yours."
            />
            {next.map((i) => (
              <NextStep key={i.key} to={readinessActionPath(site.id, i.action, homePageId)} label={i.label} hint={i.hint} />
            ))}
            <NextStep to={`/cappe/sites/${site.id}`} label="Change how your store looks" hint="Colours, fonts, pages and your logo." />
          </ul>
        </section>
      </div>
    </div>
  )
}

function NextStep({ to, label, hint }: { to: string; label: string; hint?: string | null }) {
  return (
    <li>
      <Link to={to} className="flex items-center gap-3 px-4 py-3 hover:bg-zinc-800/60">
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium text-zinc-200">{label}</span>
          {hint && <span className="mt-0.5 block text-xs text-zinc-500">{hint}</span>}
        </span>
        <ArrowRight className="h-4 w-4 shrink-0 text-zinc-500" />
      </Link>
    </li>
  )
}
