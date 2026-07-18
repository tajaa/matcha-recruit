import { useCallback, useEffect, useState } from 'react'
import { Loader2, Check } from 'lucide-react'
import { cancelLiteAddon, createLiteAddonCheckout, fetchLiteAddons, type LiteAddonInfo } from '../../api/billing/liteAddons'
import { useToast } from '../ui/Toast'

/** Add-ons section for Lite-family tenants on the Company page (`/app/company#addons`).
 *  Callers gate rendering on signup_source — the panel itself just lists what
 *  the backend says this company can buy, owns, or isn't eligible for. */
export default function LiteAddonsPanel() {
  const [addons, setAddons] = useState<LiteAddonInfo[] | null>(null)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const { toast } = useToast()

  const load = useCallback(() => {
    fetchLiteAddons().then(setAddons).catch(() => setAddons([]))
  }, [])

  useEffect(() => { load() }, [load])

  async function handleBuy(addon: LiteAddonInfo) {
    setBusyKey(addon.key)
    try {
      const { checkout_url } = await createLiteAddonCheckout(
        addon.key,
        `${window.location.origin}/app/company?addon=${addon.key}`,
        window.location.href,
      )
      window.location.href = checkout_url
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to start checkout', 'error')
      setBusyKey(null)
    }
  }

  async function handleCancel(addon: LiteAddonInfo) {
    setBusyKey(addon.key)
    try {
      const res = await cancelLiteAddon(addon.key)
      toast(res.message, 'info')
      load()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to cancel add-on', 'error')
    } finally {
      setBusyKey(null)
    }
  }

  if (addons === null) {
    return (
      <div className="text-sm text-zinc-500 flex items-center gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading add-ons…
      </div>
    )
  }
  if (addons.length === 0) return null

  return (
    <div id="addons" className="space-y-3">
      {addons.map((addon) => (
        <div
          key={addon.key}
          className={`flex items-start justify-between gap-4 rounded-lg border p-4 ${
            addon.status === 'not_eligible'
              ? 'border-zinc-800/60 bg-zinc-900/40 opacity-60'
              : 'border-zinc-800 bg-zinc-900'
          }`}
        >
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-medium text-zinc-200">{addon.name}</h4>
              {addon.status === 'active' && (
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
                  <Check className="w-3 h-3" /> Active
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-zinc-500">{addon.description}</p>
            {addon.status === 'not_eligible' && (
              <p className="mt-1 text-xs text-zinc-600 italic">Not available on your plan</p>
            )}
          </div>
          <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
            {addon.monthly_price_cents != null && addon.status !== 'active' && (
              <span className="text-xs text-zinc-400">
                <span className="text-zinc-100 font-medium">${(addon.monthly_price_cents / 100).toFixed(2)}</span>/month
              </span>
            )}
            {addon.status === 'available' && (
              <button
                type="button"
                onClick={() => handleBuy(addon)}
                disabled={busyKey !== null}
                className="bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-xs font-medium px-3 py-1.5 rounded transition-colors flex items-center gap-1.5"
              >
                {busyKey === addon.key && <Loader2 className="w-3 h-3 animate-spin" />}
                Add
              </button>
            )}
            {addon.status === 'active' && addon.cancellable && (
              <button
                type="button"
                onClick={() => handleCancel(addon)}
                disabled={busyKey !== null}
                className="text-xs text-zinc-500 hover:text-red-400 transition-colors flex items-center gap-1.5"
              >
                {busyKey === addon.key && <Loader2 className="w-3 h-3 animate-spin" />}
                Cancel
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
