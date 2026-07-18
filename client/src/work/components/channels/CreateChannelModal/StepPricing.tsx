import { Shield } from 'lucide-react'
import { PRICE_SUGGESTIONS } from './constants'

/* ─── Step 3: Pricing ─── */

export function StepPricing({
  priceDollars, setPriceDollars,
}: {
  priceDollars: string
  setPriceDollars: (v: string) => void
}) {
  const currentPrice = priceDollars ? parseFloat(priceDollars) : 0

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-zinc-400 mb-1.5">Monthly subscription price</label>
        <div className="flex items-center gap-2">
          <span className="text-zinc-400 text-lg">$</span>
          <input
            type="number"
            min="0.50"
            step="0.50"
            value={priceDollars}
            onChange={(e) => setPriceDollars(e.target.value)}
            placeholder="0.00"
            autoFocus
            className="w-32 px-3 py-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-lg font-medium placeholder:text-zinc-600 focus:outline-none focus:border-emerald-600"
          />
          <span className="text-zinc-500 text-sm">/ month</span>
        </div>
        {priceDollars !== '' && currentPrice < 0.5 && (
          <p className="text-amber-400 text-xs mt-1.5">Minimum price is $0.50</p>
        )}
      </div>

      <div>
        <label className="block text-xs text-zinc-400 mb-2">Suggested prices</label>
        <div className="flex flex-wrap gap-2">
          {PRICE_SUGGESTIONS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPriceDollars(String(p))}
              className={`px-3 py-1.5 rounded-lg border text-sm font-medium transition-colors ${
                currentPrice === p
                  ? 'border-emerald-600 bg-emerald-600/10 text-emerald-400'
                  : 'border-zinc-700 bg-zinc-800 text-zinc-300 hover:border-zinc-600'
              }`}
            >
              ${p}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-2 p-3 bg-zinc-800/50 rounded-lg border border-zinc-700/50">
        <Shield size={14} className="text-zinc-400 mt-0.5 flex-shrink-0" />
        <p className="text-xs text-zinc-400 leading-relaxed">
          Members will be charged monthly via Stripe. Subscription revenue is held by the platform — creator payouts are coming soon. Pricing can be changed later but won't affect existing subscriptions.
        </p>
      </div>
    </div>
  )
}
