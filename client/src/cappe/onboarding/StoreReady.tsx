import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowRight, Check, ExternalLink, ImagePlus, Loader2, Plus, Rocket } from 'lucide-react'
import { cappeApi } from '../api'
import { cappeSiteHost } from '../host'
import { formatCents } from '../pages/landing/shared'
import { readinessActionPath } from '../utils/readinessAction'
import type { CappePage, CappeProduct, CappeReadiness, CappeSite } from '../types'

// Where the wizard's quick store lands (/cappe/sites/:siteId/ready): the
// private storefront preview, followed by the details needed before launch.

// Checklist items this page already answers by showing the store.
const SHOWN_HERE = new Set(['content', 'offering', 'sell_on_page'])

export default function StoreReady() {
  const { siteId = '' } = useParams()
  return <StoreReadyContent key={siteId} siteId={siteId} />
}

function StoreReadyContent({ siteId }: { siteId: string }) {
  const [site, setSite] = useState<CappeSite | null>(null)
  const [products, setProducts] = useState<CappeProduct[]>([])
  const [readiness, setReadiness] = useState<CappeReadiness | null>(null)
  const [homePageId, setHomePageId] = useState<string | undefined>()
  const [loadError, setLoadError] = useState<string | null>(null)
  const [preview, setPreview] = useState('')
  const [previewError, setPreviewError] = useState(false)
  const [retry, setRetry] = useState(0)
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
        setProducts(p.filter((x) => x.status !== 'archived'))
        setReadiness(r)
        const home = pages.find((page) => page.slug === 'home') ?? pages[0]
        setHomePageId(home?.id)
        if (home) {
          cappeApi.postHtml(`/sites/${siteId}/preview`, {
            title: home.title, slug: home.slug, content: home.content, include_draft_products: true,
          }).then((html) => { if (alive) setPreview(html) })
            .catch(() => { if (alive) setPreviewError(true) })
        } else setPreviewError(true)
      })
      .catch((e) => { if (alive) setLoadError(e instanceof Error ? e.message : 'Could not load your store.') })
    return () => { alive = false }
  }, [siteId, retry])

  async function publish() {
    if (publishing || !readiness?.ready) return
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
  const missing = readiness.items.filter((i) => i.required && !i.done)
  const next = readiness.items.filter((i) => !i.required && !i.done && !SHOWN_HERE.has(i.key))
  const shop = `/cappe/sites/${site.id}/shop`

  return (
    <div className="min-h-full bg-zinc-950 bg-[radial-gradient(60rem_40rem_at_50%_-10%,rgba(198,241,107,0.08),transparent)] px-4 py-10">
      <div className="mx-auto w-full max-w-5xl">
        <div className="mb-8 text-center">
          <span className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-lime-400 text-zinc-950 shadow-lg shadow-lime-500/20">
            <Check className="h-6 w-6" />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">
            {live ? `${site.name} is live` : `${site.name} — your store is taking shape`}
          </h1>
          <p className="mt-1 text-sm text-zinc-400">
            {live ? (
              <>Anyone can shop at <a href={`https://${host}`} target="_blank" rel="noreferrer" className="text-lime-400 hover:text-lime-300">{host}</a></>
            ) : (
              <>Your draft is private. Review your products and finish the details below before publishing.</>
            )}
          </p>
        </div>

        <section aria-label="Your storefront preview" className="mb-6 overflow-hidden rounded-2xl border border-zinc-800 bg-white">
          <div className="flex items-center justify-between gap-3 bg-zinc-900 px-5 py-3 text-xs text-zinc-400">
            <span>{host} · Private preview</span>
            <Link to={`/cappe/sites/${site.id}`} className="text-lime-400">Edit your design</Link>
          </div>
          {!products.length && <p className="bg-zinc-900 px-5 pb-3 text-xs text-zinc-400">Example products show how your shop will look. They are never added to your catalog.</p>}
          {preview ? <iframe title="Your store preview" srcDoc={preview} sandbox="allow-scripts" className="h-[640px] w-full border-0" />
            : previewError ? <div className="p-8 text-center text-sm text-zinc-700">
              <p>Your preview could not load. Your draft is saved.</p>
              <button type="button" onClick={() => { setPreviewError(false); setRetry((n) => n + 1) }} className="mt-2 underline">Retry preview</button>
            </div> : <div className="flex justify-center p-12"><Loader2 className="h-6 w-6 animate-spin text-zinc-500" /></div>}
        </section>

        <section className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-xl shadow-black/40">
          <h2 className="mb-3 text-sm font-semibold text-zinc-200">Your products</h2>
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
                  {p.status === 'draft' && <Link to={shop} className="text-xs text-amber-300">Draft · review before selling</Link>}
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
                disabled={publishing || !readiness.ready}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-lime-400 px-4 py-2.5 text-sm font-semibold text-zinc-950 hover:bg-lime-300 disabled:opacity-60"
              >
                {publishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
                Publish my store
              </button>
            )}
            {!live && missing.length > 0 && <div className="mt-4">
              <h2 className="mb-2 text-sm font-medium text-zinc-200">Before you publish</h2>
              <ul className="divide-y divide-zinc-800">
                {missing.map((i) => <NextStep key={i.key} to={readinessActionPath(site.id, i.action, homePageId)} label={i.label} hint={i.hint} />)}
              </ul>
            </div>}
            {publishError && <p role="alert" className="mt-2 text-sm text-red-400">{publishError}</p>}
          </div>
        </section>

        <section className="mt-6">
          <h2 className="mb-2 px-1 text-xs font-medium uppercase tracking-wide text-zinc-500">When you're ready</h2>
          <ul className="divide-y divide-zinc-800 rounded-2xl border border-zinc-800 bg-zinc-900">
            {!missing.some((i) => i.key === 'policies') && <NextStep
              to={readinessActionPath(site.id, 'policies')}
              label="Review your return and shipping policies"
              hint="Start with our editable text and confirm the policies that fit your store."
            />}
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
