import { AdminPageHeader } from '../../components/admin/AdminPageHeader'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink, Info, Loader2 } from 'lucide-react'
import { useAsync } from '../../hooks/useAsync'
import { ApiError, api } from '../../api/client'
import { Button, Card, useToast } from '../../components/ui'
import type { MatchaLiteProductCode } from '../../api/billing/matchaLitePricing'
import { formatPrice } from '../../utils/format'
import { productPriceDollars } from '../../utils/tier'
import { PricingForm } from './MatchaLitePricingPanel'

/**
 * Every price we are still experimenting with, in one place.
 *
 * No company product uses a stored Stripe Price: each checkout builds its
 * price inline from these rows at the moment the session is created, so a save
 * here is what the next Stripe checkout charges — nothing to sync. Current
 * subscribers keep the amount they signed up at.
 *
 * - Incident reporting + Espresso: matcha_lite_pricing rows (the same form as
 *   Signup Links → Pricing).
 * - Scheduling (and any other product-builder product): the price_cents of a
 *   product_definitions row, via the price-only PUT /admin/products/{id}/price.
 */

type PaidModel = 'per_seat' | 'per_location' | 'block' | 'flat'

type AdminProduct = {
  id: string
  slug: string
  name: string
  features: Record<string, boolean>
  pricing_model: PaidModel | 'free' | 'contact_sales'
  price_cents: number | null
  block_size: number | null
  min_headcount: number
  max_headcount: number
  status: 'draft' | 'published' | 'archived'
  updated_at: string | null
}

const PAID_MODELS: readonly string[] = ['per_seat', 'per_location', 'block', 'flat']

const LITE_PLANS: { code: MatchaLiteProductCode; name: string; blurb: string }[] = [
  { code: 'matcha_lite', name: 'Matcha Lite', blurb: 'Incident reporting with the employee roster' },
  { code: 'matcha_lite_essentials', name: 'Lite Essentials', blurb: 'Incident reporting, no roster' },
]

const ESPRESSO_PLANS: { code: MatchaLiteProductCode; name: string; blurb: string }[] = [
  { code: 'espresso_lite', name: 'Espresso Lite', blurb: 'Personal plan, web paywall and the Mac app' },
  { code: 'espresso_pro', name: 'Espresso Pro', blurb: 'Personal plan, web paywall and the Mac app' },
]

/** A checkout-sized worked example, priced by the signup page's own formula
 *  (productPriceDollars) at a headcount the product actually sells. */
function exampleCharge(product: AdminProduct, cents: number): string | null {
  const model = product.pricing_model as PaidModel
  const headcount = Math.min(Math.max(25, product.min_headcount), product.max_headcount)
  const dollars = productPriceDollars({ ...product, pricing_model: model, price_cents: cents }, headcount, 3)
  if (dollars === null) return null
  if (model === 'flat') return `${formatPrice(dollars)}/month`
  if (model === 'per_location') return `${formatPrice(dollars)}/month for 3 locations`
  return `${formatPrice(dollars)}/month for ${headcount} employees`
}

function unitLabel(p: AdminProduct): string {
  if (p.pricing_model === 'per_seat') return 'per employee / month'
  if (p.pricing_model === 'per_location') return 'per location / month'
  if (p.pricing_model === 'block') return `per ${p.block_size ?? 1} employees / month`
  return 'per month'
}

function Section({ title, blurb, children }: { title: string; blurb: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="text-sm font-medium text-zinc-300">{title}</h2>
      <p className="mt-1 mb-4 text-xs text-zinc-500">{blurb}</p>
      {children}
    </section>
  )
}

function PlanCard({ name, blurb, code }: { name: string; blurb: string; code: MatchaLiteProductCode }) {
  return (
    <div>
      <p className="text-sm font-medium text-zinc-100">{name}</p>
      <p className="mb-3 text-xs text-zinc-500">{blurb}</p>
      <PricingForm productCode={code} />
    </div>
  )
}

function ProductPriceCard({
  product,
  onSaved,
  onStale,
}: {
  product: AdminProduct
  onSaved: (p: AdminProduct) => void
  onStale: () => void
}) {
  const { toast } = useToast()
  const [dollars, setDollars] = useState(String((product.price_cents ?? 0) / 100))
  const [saving, setSaving] = useState(false)
  const value = parseFloat(dollars)
  const cents = Math.round(value * 100)
  const valid = !isNaN(value) && cents > 0
  const changed = valid && cents !== product.price_cents
  const example = valid ? exampleCharge(product, cents) : null

  async function save() {
    setSaving(true)
    try {
      const saved = await api.put<AdminProduct>(`/admin/products/${product.id}/price`, {
        price_cents: cents,
        // Also editable in Products: refuse rather than overwrite a newer save.
        expected_updated_at: product.updated_at,
      })
      onSaved(saved)
      toast(`${product.name} now ${formatPrice(cents / 100)} ${unitLabel(saved)}`, 'success')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Price change failed', 'error')
      if (e instanceof ApiError && e.status === 409) onStale()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-zinc-100">{product.name}</p>
          <p className="truncate text-xs text-zinc-500">/p/{product.slug}/signup</p>
        </div>
        <a
          href={`/p/${product.slug}/signup`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex shrink-0 items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300"
        >
          Signup page <ExternalLink className="h-3 w-3" />
        </a>
      </div>
      <label className="block">
        <span className="text-xs uppercase tracking-wide text-zinc-400">Price ($) {unitLabel(product)}</span>
        <input
          type="number"
          min={0}
          step="0.01"
          value={dollars}
          onChange={(e) => setDollars(e.target.value)}
          className="mt-1 w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 focus:border-emerald-700 focus:outline-none"
        />
      </label>
      {example && (
        <p className="text-xs text-zinc-400">
          Next checkout charges <span className="font-medium text-zinc-100">{example}</span>
        </p>
      )}
      <div className="flex items-center justify-between gap-3">
        <Link to="/admin/products" className="text-xs text-zinc-500 hover:text-zinc-300">
          Features, limits and status in Products
        </Link>
        <Button size="sm" onClick={save} disabled={!changed || saving}>
          {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {changed ? 'Save price' : 'Saved'}
        </Button>
      </div>
    </Card>
  )
}

export default function Pricing() {
  const products = useAsync(
    () => api.get<{ products: AdminProduct[] }>('/admin/products').then((r) => r.products),
    [],
    [] as AdminProduct[],
  )
  const billed = products.data.filter((p) => p.status === 'published' && PAID_MODELS.includes(p.pricing_model))
  const scheduling = billed.filter((p) => p.features.employee_schedule)
  const other = billed.filter((p) => !p.features.employee_schedule)

  const replace = (saved: AdminProduct) =>
    products.setData((prev) => prev.map((p) => (p.id === saved.id ? { ...p, ...saved } : p)))

  const productGrid = (list: AdminProduct[]) => (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {/* Keyed by version too, so a reload after a 409 resets the input to the saved price. */}
      {list.map((p) => (
        <ProductPriceCard key={`${p.id}:${p.updated_at}`} product={p} onSaved={replace} onStale={products.reload} />
      ))}
    </div>
  )

  return (
    <div>
      <AdminPageHeader title="Pricing" description="What each product charges at Stripe checkout." />

      <div className="mt-6 flex items-start gap-3 rounded-lg border border-emerald-900/50 bg-emerald-950/20 px-4 py-3 text-sm text-emerald-100">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
        <p>
          A save here is what the next Stripe checkout charges. There is nothing to sync in Stripe.
          Current subscribers keep the price they signed up at.
        </p>
      </div>

      <div className="mt-10 space-y-12">
        <Section
          title="Incident reporting"
          blurb="Matcha Lite and Essentials share /lite/signup; checkout prices the company's headcount in blocks."
        >
          <div className="grid gap-6 lg:grid-cols-2">
            {LITE_PLANS.map((plan) => <PlanCard key={plan.code} {...plan} />)}
          </div>
        </Section>

        <Section
          title="Scheduling"
          blurb="Published product-builder products with scheduling. The landing page's Start now price reads this too."
        >
          {products.loading && !products.data.length ? (
            <div className="flex items-center gap-2 text-sm text-zinc-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading products…
            </div>
          ) : products.error ? (
            <p className="text-sm text-red-400">{products.error}</p>
          ) : scheduling.length ? (
            productGrid(scheduling)
          ) : (
            <p className="text-sm text-zinc-500">No published scheduling product is billed through Stripe.</p>
          )}
        </Section>

        <Section title="Espresso" blurb="Personal plans. The web paywall and the Mac app show these prices.">
          <div className="grid gap-6 lg:grid-cols-2">
            {ESPRESSO_PLANS.map((plan) => <PlanCard key={plan.code} {...plan} />)}
          </div>
        </Section>

        {other.length > 0 && (
          <Section title="Other products" blurb="Every other published product-builder product billed through Stripe.">
            {productGrid(other)}
          </Section>
        )}

        <p className="text-xs text-zinc-500">
          Compliance, the Lite add-ons and Tell-Us are priced in{' '}
          <Link to="/admin/matcha-lite" className="text-zinc-300 hover:text-zinc-100">Signup Links → Pricing</Link>.
        </p>
      </div>
    </div>
  )
}
