import { useMemo, useState } from 'react'
import { Boxes, Check, Copy, Loader2, Plus, RefreshCw } from 'lucide-react'
import { useAsync } from '../../hooks/useAsync'
import { api } from '../../api/client'
import { Badge, Button, Input, Select, Textarea, Toggle, useToast } from '../../components/ui'
import { FEATURE_GROUPS, FEATURE_LABELS } from '../../data/featureCatalog'
import { PRODUCT_NAV_CATALOG } from '../../data/productNavCatalog'

/**
 * Product builder — compose a sellable package from the modular feature flags.
 *
 * Publishing a product makes /p/<slug>/signup live; tenants who sign up there
 * get signup_source 'product:<slug>' and the sidebar is derived from the same
 * feature list (see data/productNavCatalog.ts). Grants are materialized at
 * signup/payment, so editing a live product needs the explicit "Sync tenants"
 * action to reach the companies already on it.
 */

type PricingModel = 'per_seat' | 'block' | 'flat' | 'free' | 'contact_sales'

type Product = {
  id: string
  slug: string
  name: string
  description: string
  features: Record<string, boolean>
  gate_feature: string | null
  pricing_model: PricingModel
  price_cents: number | null
  block_size: number | null
  min_headcount: number
  max_headcount: number
  nav: { feature: string; label?: string }[] | null
  status: 'draft' | 'published' | 'archived'
  updated_at: string | null
  updated_by: string | null
  tenants: { total: number; active: number }
}

type ProductsResponse = {
  products: Product[]
  available_features: string[]
  pricing_models: PricingModel[]
}

const PRICING_OPTIONS = [
  { value: 'per_seat', label: 'Per seat (per employee / month)' },
  { value: 'block', label: 'Per block of employees' },
  { value: 'flat', label: 'Flat monthly' },
  { value: 'free', label: 'Free (activates at signup)' },
  { value: 'contact_sales', label: 'Contact sales (admin activates)' },
]

const PAID_MODELS: PricingModel[] = ['per_seat', 'block', 'flat']

type Draft = {
  slug: string
  name: string
  description: string
  features: Record<string, boolean>
  gate_feature: string
  pricing_model: PricingModel
  price_dollars: string
  block_size: string
  min_headcount: string
  max_headcount: string
  navOrder: string[]
}

function emptyDraft(): Draft {
  return {
    slug: '', name: '', description: '', features: {}, gate_feature: '',
    pricing_model: 'per_seat', price_dollars: '', block_size: '10',
    min_headcount: '1', max_headcount: '300', navOrder: [],
  }
}

function toDraft(p: Product): Draft {
  const enabled = Object.entries(p.features).filter(([, v]) => v).map(([k]) => k)
  return {
    slug: p.slug,
    name: p.name,
    description: p.description,
    features: { ...p.features },
    gate_feature: p.gate_feature ?? '',
    pricing_model: p.pricing_model,
    price_dollars: p.price_cents != null ? String(p.price_cents / 100) : '',
    block_size: p.block_size != null ? String(p.block_size) : '10',
    min_headcount: String(p.min_headcount),
    max_headcount: String(p.max_headcount),
    // A saved ordering wins; otherwise seed from the enabled features so the
    // reorder controls always have something to work with.
    navOrder: p.nav?.length ? p.nav.map((n) => n.feature) : enabled,
  }
}

function priceLabel(p: Product): string {
  if (p.pricing_model === 'free') return 'Free'
  if (p.pricing_model === 'contact_sales') return 'Contact sales'
  const dollars = (p.price_cents ?? 0) / 100
  if (p.pricing_model === 'flat') return `$${dollars}/mo`
  if (p.pricing_model === 'per_seat') return `$${dollars}/employee/mo`
  return `$${dollars} per ${p.block_size} employees/mo`
}

export default function Products() {
  const { data, loading, reload } = useAsync(
    () => api.get<ProductsResponse>('/admin/products'),
    [],
    { products: [], available_features: [], pricing_models: [] } as ProductsResponse,
  )
  const { toast } = useToast()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [saving, setSaving] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const products = data.products
  const selected = products.find((p) => p.id === selectedId) ?? null
  const isNew = draft !== null && selected === null

  const enabledFeatures = useMemo(
    () => (draft ? Object.entries(draft.features).filter(([, v]) => v).map(([k]) => k) : []),
    [draft],
  )

  // Only features the backend admits (DEFAULT_COMPANY_FEATURES + incidents /
  // employees) are pickable — a label in the catalog for a flag the server
  // rejects would fail on save.
  const sellable = new Set(data.available_features)

  function startNew() {
    setSelectedId(null)
    setDraft(emptyDraft())
    setError(null)
  }

  function startEdit(p: Product) {
    setSelectedId(p.id)
    setDraft(toDraft(p))
    setError(null)
  }

  function toggleFeature(key: string, on: boolean) {
    setDraft((d) => {
      if (!d) return d
      const features = { ...d.features, [key]: on }
      const navOrder = on
        ? [...d.navOrder.filter((f) => f !== key), key]
        : d.navOrder.filter((f) => f !== key)
      // Dropping the feature that was the paid gate must drop the gate too,
      // or the save 400s on "gate must be one of the enabled features".
      const gate_feature = !on && d.gate_feature === key ? '' : d.gate_feature
      return { ...d, features, navOrder, gate_feature }
    })
  }

  function moveNav(feature: string, delta: number) {
    setDraft((d) => {
      if (!d) return d
      const order = [...d.navOrder]
      const i = order.indexOf(feature)
      const j = i + delta
      if (i < 0 || j < 0 || j >= order.length) return d
      ;[order[i], order[j]] = [order[j], order[i]]
      return { ...d, navOrder: order }
    })
  }

  async function save() {
    if (!draft) return
    setSaving(true)
    setError(null)
    const paid = PAID_MODELS.includes(draft.pricing_model)
    const body = {
      slug: draft.slug.trim().toLowerCase(),
      name: draft.name.trim(),
      description: draft.description.trim(),
      features: Object.fromEntries(enabledFeatures.map((f) => [f, true])),
      gate_feature: paid ? draft.gate_feature || null : null,
      pricing_model: draft.pricing_model,
      price_cents: paid ? Math.round(parseFloat(draft.price_dollars || '0') * 100) : null,
      block_size: draft.pricing_model === 'block' ? parseInt(draft.block_size, 10) : null,
      min_headcount: parseInt(draft.min_headcount, 10) || 1,
      max_headcount: parseInt(draft.max_headcount, 10) || 300,
      nav: draft.navOrder.filter((f) => draft.features[f]).map((feature) => ({ feature })),
    }
    try {
      const saved = selected
        ? await api.put<Product>(`/admin/products/${selected.id}`, body)
        : await api.post<Product>('/admin/products', body)
      await reload()
      setSelectedId(saved.id)
      setDraft(null)
      toast(`${saved.name} saved`, 'success')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function setStatus(p: Product, status: Product['status']) {
    setBusy(true)
    try {
      await api.post(`/admin/products/${p.id}/status`, { status })
      await reload()
      toast(`${p.name} ${status}`, 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Status change failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function syncTenants(p: Product) {
    setBusy(true)
    try {
      const res = await api.post<{ updated: number; skipped_pending: number }>(
        `/admin/products/${p.id}/sync-tenants`, {},
      )
      toast(
        `${res.updated} tenant(s) updated · ${res.skipped_pending} pending skipped`,
        'success',
      )
      await reload()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Sync failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  function copyLink(p: Product) {
    navigator.clipboard.writeText(`${window.location.origin}/p/${p.slug}/signup`)
    toast('Signup link copied', 'success')
  }

  return (
    <div className="flex h-[calc(100vh-7rem)] overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      {/* Product list */}
      <div className="flex w-72 shrink-0 flex-col border-r border-white/[0.06]">
        <div className="flex items-center gap-2 border-b border-white/[0.06] px-3 py-3">
          <Boxes className="h-4 w-4 shrink-0 text-emerald-400" />
          <h1 className="text-sm font-semibold text-zinc-100">Products</h1>
        </div>
        <div className="border-b border-white/[0.06] p-2">
          <Button size="sm" onClick={startNew} className="w-full">
            <Plus className="h-3.5 w-3.5" /> New product
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-3"><Loader2 className="h-4 w-4 animate-spin text-zinc-500" /></div>
          ) : products.length === 0 ? (
            <p className="p-3 text-xs text-zinc-500">No products yet. Build one.</p>
          ) : (
            products.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => startEdit(p)}
                className={`flex w-full flex-col gap-0.5 border-l-2 px-3 py-2 text-left transition-colors ${
                  selectedId === p.id ? 'border-emerald-400 bg-white/[0.05]' : 'border-transparent hover:bg-white/[0.03]'
                }`}
              >
                <span className="truncate text-[13px] text-zinc-200">{p.name}</span>
                <span className="flex items-center gap-1.5 text-[11px] text-zinc-500">
                  <Badge variant={p.status === 'published' ? 'success' : 'neutral'}>{p.status}</Badge>
                  {p.tenants.active}/{p.tenants.total} active
                </span>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Editor */}
      <div className="flex flex-1 flex-col overflow-y-auto">
        {!draft ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-sm text-zinc-500">
            {selected ? (
              <ProductSummary
                product={selected}
                busy={busy}
                onEdit={() => startEdit(selected)}
                onStatus={setStatus}
                onSync={syncTenants}
                onCopyLink={copyLink}
              />
            ) : (
              <p>Select a product, or build a new one.</p>
            )}
          </div>
        ) : (
          <div className="space-y-6 p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-zinc-100">
                {isNew ? 'New product' : `Editing ${selected?.name}`}
              </h2>
              <div className="flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => setDraft(null)}>Cancel</Button>
                <Button size="sm" onClick={save} disabled={saving}>
                  {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save
                </Button>
              </div>
            </div>

            {error && (
              <p className="rounded border border-red-900/30 bg-red-950/30 px-3 py-2 text-sm text-red-400">{error}</p>
            )}

            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Product name"
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                placeholder="Safety Pro"
              />
              <Input
                label="Slug (signup URL)"
                value={draft.slug}
                disabled={!isNew && (selected?.tenants.total ?? 0) > 0}
                onChange={(e) => setDraft({ ...draft, slug: e.target.value })}
                placeholder="safety-pro"
              />
            </div>
            <p className="-mt-3 text-[11px] text-zinc-500">
              Signup link: <span className="font-mono text-zinc-400">/p/{draft.slug || '<slug>'}/signup</span>
              {!isNew && (selected?.tenants.total ?? 0) > 0 && ' · locked — companies already signed up on it'}
            </p>

            <Textarea
              label="Description"
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              placeholder="What the customer gets, in one line."
              rows={2}
            />

            {/* Pricing */}
            <section className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Pricing</h3>
              <div className="grid grid-cols-2 gap-3">
                <Select
                  label="Model"
                  options={PRICING_OPTIONS}
                  value={draft.pricing_model}
                  onChange={(e) => setDraft({ ...draft, pricing_model: e.target.value as PricingModel })}
                />
                {PAID_MODELS.includes(draft.pricing_model) && (
                  <Input
                    label={draft.pricing_model === 'flat' ? 'Price / month ($)'
                      : draft.pricing_model === 'per_seat' ? 'Price / employee / month ($)'
                      : 'Price per block / month ($)'}
                    value={draft.price_dollars}
                    onChange={(e) => setDraft({ ...draft, price_dollars: e.target.value })}
                    placeholder="3"
                  />
                )}
                {draft.pricing_model === 'block' && (
                  <Input
                    label="Employees per block"
                    value={draft.block_size}
                    onChange={(e) => setDraft({ ...draft, block_size: e.target.value })}
                  />
                )}
                {PAID_MODELS.includes(draft.pricing_model) && (
                  <>
                    <Input
                      label="Min headcount"
                      value={draft.min_headcount}
                      onChange={(e) => setDraft({ ...draft, min_headcount: e.target.value })}
                    />
                    <Input
                      label="Max headcount"
                      value={draft.max_headcount}
                      onChange={(e) => setDraft({ ...draft, max_headcount: e.target.value })}
                    />
                  </>
                )}
              </div>
              {PAID_MODELS.includes(draft.pricing_model) && (
                <Select
                  label="Paid gate feature"
                  options={enabledFeatures.map((f) => ({ value: f, label: FEATURE_LABELS[f] ?? f }))}
                  value={draft.gate_feature}
                  onChange={(e) => setDraft({ ...draft, gate_feature: e.target.value })}
                  placeholder="Select the flag Stripe turns on"
                />
              )}
              {PAID_MODELS.includes(draft.pricing_model) && (
                <p className="text-[11px] text-zinc-500">
                  Everything stays off until Stripe confirms payment; this flag is what the
                  webhook flips (like <span className="font-mono">incidents</span> for Matcha Lite).
                </p>
              )}
            </section>

            {/* Features */}
            <section className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">
                Included features ({enabledFeatures.length})
              </h3>
              {FEATURE_GROUPS.map((group) => {
                const keys = Object.keys(group.features).filter((k) => sellable.has(k))
                if (keys.length === 0) return null
                return (
                  <div key={group.label} className="space-y-1.5">
                    <p className="text-[11px] uppercase tracking-wide text-zinc-600">{group.label}</p>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                      {keys.map((key) => (
                        <label key={key} className="flex items-center gap-2 py-0.5 text-[13px] text-zinc-300">
                          <Toggle
                            size="sm"
                            checked={!!draft.features[key]}
                            onChange={(on) => toggleFeature(key, on)}
                          />
                          <span className="truncate" title={FEATURE_LABELS[key]}>{FEATURE_LABELS[key]}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )
              })}
            </section>

            {/* Nav preview */}
            <section className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Sidebar</h3>
              <p className="text-[11px] text-zinc-500">
                Derived from the features above. Reorder to change what the customer sees;
                features with no page of their own don't appear.
              </p>
              <div className="max-w-xs space-y-1 rounded-lg border border-white/[0.06] bg-white/[0.02] p-2">
                {draft.navOrder.filter((f) => draft.features[f] && PRODUCT_NAV_CATALOG[f]).map((f, i, arr) => (
                  <div key={f} className="flex items-center justify-between gap-2 rounded px-2 py-1 text-[13px] text-zinc-300 hover:bg-white/[0.04]">
                    <span className="truncate">{PRODUCT_NAV_CATALOG[f].label}</span>
                    <span className="flex gap-1">
                      <button type="button" disabled={i === 0} onClick={() => moveNav(f, -1)}
                        className="text-zinc-500 hover:text-zinc-200 disabled:opacity-30">↑</button>
                      <button type="button" disabled={i === arr.length - 1} onClick={() => moveNav(f, 1)}
                        className="text-zinc-500 hover:text-zinc-200 disabled:opacity-30">↓</button>
                    </span>
                  </div>
                ))}
                <div className="flex items-center gap-2 rounded px-2 py-1 text-[13px] text-zinc-500">Company</div>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  )
}

function ProductSummary({
  product, busy, onEdit, onStatus, onSync, onCopyLink,
}: {
  product: Product
  busy: boolean
  onEdit: () => void
  onStatus: (p: Product, status: Product['status']) => void
  onSync: (p: Product) => void
  onCopyLink: (p: Product) => void
}) {
  const enabled = Object.entries(product.features).filter(([, v]) => v).map(([k]) => k)
  return (
    <div className="w-full max-w-xl space-y-4 p-5 text-left">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-zinc-100">{product.name}</h2>
          <p className="text-xs text-zinc-500">{product.description || 'No description'}</p>
        </div>
        <Badge variant={product.status === 'published' ? 'success' : 'neutral'}>{product.status}</Badge>
      </div>

      <div className="grid grid-cols-2 gap-3 text-[13px] text-zinc-300">
        <div><span className="text-zinc-500">Price</span><br />{priceLabel(product)}</div>
        <div>
          <span className="text-zinc-500">Tenants</span><br />
          {product.tenants.active} active / {product.tenants.total} total
        </div>
        <div className="col-span-2">
          <span className="text-zinc-500">Signup link</span><br />
          <span className="font-mono text-xs text-zinc-400">/p/{product.slug}/signup</span>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {enabled.map((f) => (
          <span key={f} className="rounded border border-white/[0.08] bg-white/[0.03] px-1.5 py-0.5 text-[11px] text-zinc-400">
            {FEATURE_LABELS[f] ?? f}
          </span>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={onEdit}>Edit</Button>
        <Button size="sm" variant="secondary" onClick={() => onCopyLink(product)}>
          <Copy className="h-3.5 w-3.5" /> Copy link
        </Button>
        {product.status !== 'published' ? (
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => onStatus(product, 'published')}>
            <Check className="h-3.5 w-3.5" /> Publish
          </Button>
        ) : (
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => onStatus(product, 'archived')}>
            Archive
          </Button>
        )}
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => onSync(product)}>
          <RefreshCw className="h-3.5 w-3.5" /> Sync tenants
        </Button>
      </div>
      <p className="text-[11px] text-zinc-500">
        Feature grants are written at signup/payment. "Sync tenants" re-applies this product to
        companies already activated on it; pending (unpaid) companies are skipped.
      </p>
    </div>
  )
}
