import { AdminCard, AdminInput, AdminButton } from '../../../components/admin/AdminUI'
import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import {
  FLAT_PLAN_CODES,
  computeLitePriceDollars,
  fetchMatchaLitePricingAdmin,
  saveMatchaLitePricingAdmin,
  type MatchaLiteProductCode,
  type MatchaLitePricingAdminConfig,
} from '../../../api/billing/matchaLitePricing'
import { formatPrice } from '../../../utils/format'

// One form per built-in plan on the Catalog workspace’s Pricing tab.
export function PricingForm({ productCode, onSaved }: { productCode: MatchaLiteProductCode; onSaved?: () => void }) {
  const [config, setConfig] = useState<MatchaLitePricingAdminConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  // Form fields in dollars for display; converted to cents on save.
  const [priceDollars, setPriceDollars] = useState('')
  const [blockSize, setBlockSize] = useState('')
  const [saleActive, setSaleActive] = useState(false)
  const [salePriceDollars, setSalePriceDollars] = useState('')
  const [minHeadcount, setMinHeadcount] = useState('')
  const [maxHeadcount, setMaxHeadcount] = useState('')

  // Compliance, the add-ons, and Tell-Us are flat per-head (or per-store)
  // pricing modeled as block_size=1 in this step-function table — lock the
  // field so an admin can't accidentally turn them back into a step function
  // (e.g. block_size=5 would silently change the effective rate without
  // changing price_per_block).
  const isFlatRate =
    productCode === 'matcha_compliance' || productCode === 'tellus_brand' || productCode.startsWith('addon_')
  // A flat monthly plan (Espresso) has no block size or headcount at all —
  // one unit, one price.
  const isFlatPlan = FLAT_PLAN_CODES.includes(productCode)
  // The table's columns say "headcount" everywhere — Tell-Us reuses them to
  // mean store count. Swap the unit word in the UI only.
  const unit = productCode === 'tellus_brand' ? 'store' : 'employee'

  useEffect(() => {
    fetchMatchaLitePricingAdmin(productCode)
      .then((c) => {
        setConfig(c)
        setPriceDollars(String(c.price_per_block_cents / 100))
        setBlockSize(String(c.block_size))
        setSaleActive(c.sale_active)
        setSalePriceDollars(c.sale_price_per_block_cents != null ? String(c.sale_price_per_block_cents / 100) : '')
        setMinHeadcount(String(c.min_headcount))
        setMaxHeadcount(String(c.max_headcount))
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load pricing'))
      .finally(() => setLoading(false))
  }, [productCode])

  const priceNum = parseFloat(priceDollars)
  const blockSizeNum = parseInt(blockSize, 10)
  const salePriceNum = salePriceDollars.trim() ? parseFloat(salePriceDollars) : null
  const minNum = parseInt(minHeadcount, 10)
  const maxNum = parseInt(maxHeadcount, 10)

  const valid =
    !isNaN(priceNum) && priceNum > 0 &&
    !isNaN(blockSizeNum) && blockSizeNum > 0 &&
    !isNaN(minNum) && minNum > 0 &&
    !isNaN(maxNum) && maxNum > 0 &&
    minNum <= maxNum &&
    (!saleActive || (salePriceNum !== null && salePriceNum > 0))

  async function handleSave() {
    if (!valid) return
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const updated = await saveMatchaLitePricingAdmin(
        {
          price_per_block_cents: Math.round(priceNum * 100),
          block_size: isFlatRate || isFlatPlan ? 1 : blockSizeNum,
          sale_price_per_block_cents: salePriceNum !== null ? Math.round(salePriceNum * 100) : null,
          sale_active: saleActive,
          min_headcount: isFlatPlan ? 1 : minNum,
          max_headcount: isFlatPlan ? 1 : maxNum,
          // This row is also editable on the other pricing page.
          expected_updated_at: config?.updated_at ?? null,
        },
        productCode,
      )
      setConfig(updated)
      onSaved?.()
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to save pricing')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="text-sm text-zinc-500 flex items-center gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading pricing…
      </div>
    )
  }

  const perHeadEquivalent =
    !isNaN(priceNum) && !isNaN(blockSizeNum) && blockSizeNum > 0 ? (priceNum / blockSizeNum).toFixed(2) : null
  const effectivePriceNum = saleActive && salePriceNum !== null ? salePriceNum : priceNum
  const effectivePerHead =
    !isNaN(effectivePriceNum) && !isNaN(blockSizeNum) && blockSizeNum > 0
      ? (effectivePriceNum / blockSizeNum).toFixed(2)
      : null
  // What the next checkout charges, with the same formula the signup pages
  // use (the server's compute_matcha_lite_price_cents).
  const sampleQuantity = isFlatPlan ? 1 : Math.min(Math.max(25, minNum || 1), maxNum || 25)
  const nextCharge =
    !isNaN(effectivePriceNum) && effectivePriceNum > 0 && blockSizeNum > 0
      ? computeLitePriceDollars(sampleQuantity, {
          block_size: isFlatRate || isFlatPlan ? 1 : blockSizeNum,
          effective_price_per_block_cents: Math.round(effectivePriceNum * 100),
        })
      : null

  return (
    <div className="max-w-lg">
      <AdminCard className="mb-4 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <label className="block">
            <span className="text-xs text-zinc-400 uppercase tracking-wide">
              {isFlatPlan ? 'Price per month ($)' : 'Price per block ($)'}
            </span>
            <AdminInput
              type="number"
              min={0}
              step="0.01"
              value={priceDollars}
              onChange={(e) => setPriceDollars(e.target.value)}
              className="mt-1"
            />
          </label>
          {!isFlatPlan && <label className="block">
            <span className="text-xs text-zinc-400 uppercase tracking-wide">Block size (employees)</span>
            <AdminInput
              type="number"
              min={1}
              step="1"
              value={isFlatRate ? '1' : blockSize}
              onChange={(e) => setBlockSize(e.target.value)}
              disabled={isFlatRate}
              className="mt-1 disabled:opacity-40 disabled:cursor-not-allowed"
            />
            {isFlatRate && <span className="block mt-1 text-xs text-zinc-500">Fixed at 1 — priced flat per {unit}</span>}
          </label>}
        </div>
        {perHeadEquivalent && !isFlatPlan && <p className="text-xs text-zinc-500">≈ ${perHeadEquivalent}/{unit}/month</p>}
        {productCode === 'tellus_brand' && (
          <p className="text-xs text-amber-500">
            Checkout mints an inline Stripe price at signup time — changing this only affects new
            checkouts. Existing brand subscriptions keep their original amount until they cancel
            and re-subscribe.
          </p>
        )}

        {!isFlatPlan && <div className="grid grid-cols-2 gap-4">
          <label className="block">
            <span className="text-xs text-zinc-400 uppercase tracking-wide">
              Min {productCode === 'tellus_brand' ? 'stores' : 'headcount'}
            </span>
            <AdminInput
              type="number"
              min={1}
              step="1"
              value={minHeadcount}
              onChange={(e) => setMinHeadcount(e.target.value)}
              className="mt-1"
            />
          </label>
          <label className="block">
            <span className="text-xs text-zinc-400 uppercase tracking-wide">
              Max {productCode === 'tellus_brand' ? 'stores' : 'headcount'}
            </span>
            <AdminInput
              type="number"
              min={1}
              step="1"
              value={maxHeadcount}
              onChange={(e) => setMaxHeadcount(e.target.value)}
              className="mt-1"
            />
          </label>
        </div>}

        <div className="border-t border-zinc-800 pt-4">
          <label className="flex items-center gap-2 mb-3 cursor-pointer">
            <input
              type="checkbox"
              checked={saleActive}
              onChange={(e) => setSaleActive(e.target.checked)}
              className="rounded border-zinc-700 bg-zinc-800 text-emerald-600 focus:ring-emerald-700"
            />
            <span className="text-sm text-zinc-300">Sale active</span>
          </label>
          <label className="block">
            <span className="text-xs text-zinc-400 uppercase tracking-wide">
              {isFlatPlan ? 'Sale price per month ($)' : 'Sale price per block ($)'}
            </span>
            <AdminInput
              type="number"
              min={0}
              step="0.01"
              value={salePriceDollars}
              onChange={(e) => setSalePriceDollars(e.target.value)}
              disabled={!saleActive}
              placeholder="e.g. 25.00"
              className="mt-1 disabled:opacity-40"
            />
          </label>
          {saleActive && effectivePerHead && !isFlatPlan && (
            <p className="mt-1 text-xs text-emerald-400">≈ ${effectivePerHead}/{unit}/month while the sale is active</p>
          )}
        </div>

        {nextCharge !== null && (
          <p className="text-xs text-zinc-400">
            Next checkout charges{' '}
            <span className="font-medium text-zinc-100">{formatPrice(nextCharge)}/month</span>
            {!isFlatPlan && ` for ${sampleQuantity} ${unit}s`}
          </p>
        )}

        {error && <p className="text-sm text-red-400">{error}</p>}

        <AdminButton
          onClick={handleSave}
          disabled={!valid || saving}
          className="w-full disabled:opacity-50 gap-2" variant="success"
        >
          {saving && <Loader2 className="w-4 h-4 animate-spin" />}
          {saved ? 'Saved' : 'Save pricing'}
        </AdminButton>

        {config?.updated_at && (
          <p className="text-xs text-zinc-600">
            Last updated {new Date(config.updated_at).toLocaleString()}
            {config.updated_by ? ` by ${config.updated_by}` : ''}
          </p>
        )}
      </AdminCard>
    </div>
  )
}
