import { useEffect, useState } from 'react'
import { CheckCircle2, ExternalLink, Loader2, RefreshCw } from 'lucide-react'
import { AdminButton, AdminCard, AdminInput, AdminSection, AdminTextarea } from './AdminUI'
import { connectStripeCatalogWebhook, fetchStripeCatalog, saveStripeCatalogDetails, syncStripeCatalog } from '../../api/admin/stripeCatalog'
import type { StripeCatalog, StripeCatalogKey, StripeCatalogProduct } from '../../types/stripeCatalog'

const LABELS = {
  synced: 'Synced', out_of_sync: 'Needs sync', error: 'Sync failed',
  not_synced: 'Not synced yet', not_configured: 'Stripe not configured', not_ready: 'Product setup required',
}

function CatalogDetails({ product, disabled, onSave }: {
  product: StripeCatalogProduct; disabled: boolean;
  onSave: (key: StripeCatalogKey, name: string, description: string) => void;
}) {
  const [name, setName] = useState(product.display_name)
  const [description, setDescription] = useState(product.description)
  const changed = name.trim() !== product.display_name || description !== product.description
  return (
    <div className="space-y-3 border-t border-zinc-800 pt-3">
      <AdminInput label="Checkout name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
      <AdminTextarea label="Checkout description" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} />
      <AdminButton variant="secondary" onClick={() => onSave(product.key, name.trim(), description)} disabled={disabled || !changed || !name.trim()}>Save product details</AdminButton>
    </div>
  )
}

export function StripeCatalogPanel({ revision = 0 }: { revision?: number }) {
  const [catalog, setCatalog] = useState<StripeCatalog | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<StripeCatalogKey | 'webhook' | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchStripeCatalog().then((data) => {
      if (!cancelled) { setCatalog(data); setError(null) }
    }).catch((e: unknown) => {
      if (!cancelled) setError(e instanceof Error ? e.message : 'Could not load Stripe catalog')
    })
    return () => { cancelled = true }
  }, [revision])

  const awaitingWebhook = catalog?.webhook.catalog_events_enabled
    ? catalog.products.filter((p) => p.status === 'synced' && !p.webhook_verified_at).map((p) => `${p.key}:${p.synced_at}`).join('|')
    : ''
  useEffect(() => {
    if (!awaitingWebhook) return
    let cancelled = false
    let attempts = 0
    const timer = window.setInterval(() => {
      if (++attempts > 24) { window.clearInterval(timer); return }
      fetchStripeCatalog().then((data) => {
        if (!cancelled) setCatalog(data)
      }).catch(() => { /* Retain the last status through a transient polling failure. */ })
    }, 5000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [awaitingWebhook])

  async function sync(key: StripeCatalogKey) {
    setBusy(key)
    setError(null)
    try {
      setCatalog(await syncStripeCatalog(key))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Stripe sync failed; your saved price is unchanged')
      // A partial failure is persisted on the server; show its retry state.
      try { setCatalog(await fetchStripeCatalog()) } catch { /* keep the actionable sync error */ }
    } finally { setBusy(null) }
  }

  async function connect() {
    setBusy('webhook')
    setError(null)
    try {
      await connectStripeCatalogWebhook()
      setCatalog(await fetchStripeCatalog())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not connect Stripe catalog webhooks')
    } finally { setBusy(null) }
  }

  async function saveDetails(key: StripeCatalogKey, name: string, description: string) {
    setBusy(key)
    setError(null)
    try {
      setCatalog(await saveStripeCatalogDetails(key, { name, description }))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not sync product details')
      try { setCatalog(await fetchStripeCatalog()) } catch { /* retain the save error */ }
    } finally { setBusy(null) }
  }

  const dashboard = `https://dashboard.stripe.com/${catalog?.livemode ? '' : 'test/'}products/`
  return (
    <AdminSection title="Stripe catalog" description="Admin prices sync to these two products. Signed Stripe webhooks confirm changes and flag differences.">
      {error && <p role="alert" className="mb-3 text-sm text-red-400">{error}</p>}
      {!catalog ? (
        !error && <p className="flex items-center gap-2 text-sm text-zinc-500"><Loader2 className="h-4 w-4 animate-spin" />Loading Stripe catalog…</p>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 text-xs text-zinc-400">
            <p>{catalog.configured ? <><span className={catalog.livemode ? 'font-medium text-amber-300' : 'text-emerald-300'}>{catalog.livemode ? 'Live mode' : 'Test mode'}</span> · {catalog.account_id}</> : 'Configure the server’s Stripe secret key to connect billing.'}</p>
            <AdminButton variant="secondary" onClick={connect} disabled={!catalog.configured || busy !== null}>
              {busy === 'webhook' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {catalog.webhook.catalog_events_enabled ? 'Check webhook connection' : 'Connect catalog webhooks'}
            </AdminButton>
          </div>
          {catalog.webhook.catalog_events_enabled && <p className="mb-4 flex items-center gap-2 text-xs text-emerald-400"><CheckCircle2 className="h-3.5 w-3.5" />Catalog events connected to your existing Stripe webhook.</p>}
          <div className="grid gap-4 md:grid-cols-2">
            {catalog.products.map((product) => (
              <AdminCard key={product.key} className="space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div><h3 className="text-sm font-medium text-zinc-100">{product.name}</h3><p className={`mt-1 text-xs ${product.status === 'synced' ? 'text-emerald-400' : 'text-amber-300'}`}>{LABELS[product.status]}</p></div>
                  <AdminButton onClick={() => sync(product.key)} disabled={!catalog.configured || busy !== null || product.status === 'not_ready'}>
                    {busy === product.key ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />} Sync
                  </AdminButton>
                </div>
                {product.error && <p className="text-xs text-red-400">{product.error}</p>}
                {product.stripe_product_id && <a className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-100" href={`${dashboard}${encodeURIComponent(product.stripe_product_id)}`} target="_blank" rel="noreferrer">View in Stripe <ExternalLink className="h-3 w-3" /></a>}
                {product.prices.length > 0 && <p className="text-xs text-zinc-500">{product.prices.length === 1 ? 'One monthly price' : `${product.prices.map((p) => p.label).join(' · ')} · monthly prices`}</p>}
                {product.status === 'synced' && <p className="text-xs text-zinc-500">{product.webhook_verified_at ? `Webhook confirmed ${new Date(product.webhook_verified_at).toLocaleString()}` : 'Saved in Stripe; awaiting webhook confirmation.'}</p>}
                <CatalogDetails key={`${product.key}:${product.display_name}:${product.description}`} product={product} disabled={!catalog.configured || busy !== null || product.status === 'not_ready'} onSave={saveDetails} />
              </AdminCard>
            ))}
          </div>
        </>
      )}
    </AdminSection>
  )
}
