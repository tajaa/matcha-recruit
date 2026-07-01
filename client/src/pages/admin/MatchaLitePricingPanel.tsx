import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import {
  fetchMatchaLitePricingAdmin,
  saveMatchaLitePricingAdmin,
  type MatchaLiteProductCode,
  type MatchaLitePricingAdminConfig,
} from '../../api/matchaLitePricing'

const PRODUCT_TABS: { code: MatchaLiteProductCode; label: string }[] = [
  { code: 'matcha_lite', label: 'Standard Lite' },
  { code: 'matcha_lite_essentials', label: 'Essentials (no roster)' },
  { code: 'matcha_compliance', label: 'Compliance' },
  { code: 'addon_voice_intake', label: 'Add-on: Voice Intake' },
  { code: 'addon_hris_sync', label: 'Add-on: HRIS Sync' },
  { code: 'addon_handbook_watch', label: 'Add-on: Handbook Watch' },
]

export default function MatchaLitePricingPanel() {
  const [productCode, setProductCode] = useState<MatchaLiteProductCode>('matcha_lite')

  return (
    <div>
      <div className="flex flex-wrap gap-1 mb-4">
        {PRODUCT_TABS.map((tab) => (
          <button
            key={tab.code}
            onClick={() => setProductCode(tab.code)}
            className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
              productCode === tab.code ? 'bg-emerald-700 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {/* key forces a clean remount/refetch on switch instead of threading
          productCode through every field's state */}
      <PricingForm key={productCode} productCode={productCode} />
    </div>
  )
}

function PricingForm({ productCode }: { productCode: MatchaLiteProductCode }) {
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

  // Compliance and the add-ons are flat per-head pricing modeled as
  // block_size=1 in this step-function table — lock the field so an admin
  // can't accidentally turn them back into a step function (e.g. block_size=5
  // would silently change the effective rate without changing price_per_block).
  const isFlatRate = productCode === 'matcha_compliance' || productCode.startsWith('addon_')

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
          block_size: isFlatRate ? 1 : blockSizeNum,
          sale_price_per_block_cents: salePriceNum !== null ? Math.round(salePriceNum * 100) : null,
          sale_active: saleActive,
          min_headcount: minNum,
          max_headcount: maxNum,
        },
        productCode,
      )
      setConfig(updated)
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

  return (
    <div className="max-w-lg">
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 mb-4 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <label className="block">
            <span className="text-xs text-zinc-400 uppercase tracking-wide">Price per block ($)</span>
            <input
              type="number"
              min={0}
              step="0.01"
              value={priceDollars}
              onChange={(e) => setPriceDollars(e.target.value)}
              className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
            />
          </label>
          <label className="block">
            <span className="text-xs text-zinc-400 uppercase tracking-wide">Block size (employees)</span>
            <input
              type="number"
              min={1}
              step="1"
              value={isFlatRate ? '1' : blockSize}
              onChange={(e) => setBlockSize(e.target.value)}
              disabled={isFlatRate}
              className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed"
            />
            {isFlatRate && <span className="block mt-1 text-xs text-zinc-500">Fixed at 1 — priced flat per employee</span>}
          </label>
        </div>
        {perHeadEquivalent && <p className="text-xs text-zinc-500">≈ ${perHeadEquivalent}/employee/month</p>}

        <div className="grid grid-cols-2 gap-4">
          <label className="block">
            <span className="text-xs text-zinc-400 uppercase tracking-wide">Min headcount</span>
            <input
              type="number"
              min={1}
              step="1"
              value={minHeadcount}
              onChange={(e) => setMinHeadcount(e.target.value)}
              className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
            />
          </label>
          <label className="block">
            <span className="text-xs text-zinc-400 uppercase tracking-wide">Max headcount</span>
            <input
              type="number"
              min={1}
              step="1"
              value={maxHeadcount}
              onChange={(e) => setMaxHeadcount(e.target.value)}
              className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
            />
          </label>
        </div>

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
            <span className="text-xs text-zinc-400 uppercase tracking-wide">Sale price per block ($)</span>
            <input
              type="number"
              min={0}
              step="0.01"
              value={salePriceDollars}
              onChange={(e) => setSalePriceDollars(e.target.value)}
              disabled={!saleActive}
              placeholder="e.g. 25.00"
              className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700 disabled:opacity-40"
            />
          </label>
          {saleActive && effectivePerHead && (
            <p className="mt-1 text-xs text-emerald-400">≈ ${effectivePerHead}/employee/month while the sale is active</p>
          )}
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button
          onClick={handleSave}
          disabled={!valid || saving}
          className="w-full bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm font-medium py-2.5 rounded transition-colors flex items-center justify-center gap-2"
        >
          {saving && <Loader2 className="w-4 h-4 animate-spin" />}
          {saved ? 'Saved' : 'Save pricing'}
        </button>

        {config?.updated_at && (
          <p className="text-xs text-zinc-600">
            Last updated {new Date(config.updated_at).toLocaleString()}
            {config.updated_by ? ` by ${config.updated_by}` : ''}
          </p>
        )}
      </div>
    </div>
  )
}
