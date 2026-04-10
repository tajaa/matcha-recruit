import { Hash, Loader2, Info, AlertTriangle } from 'lucide-react'

interface Props {
  channelName: string
  priceCents: number
  currency: string
  inactivityDays: number | null
  cooldownUntil: string | null
  canRejoin: boolean
  onCheckout: () => void
  checkingOut: boolean
  onBack: () => void
}

export default function PaidChannelGate({
  channelName,
  priceCents,
  currency,
  inactivityDays,
  cooldownUntil,
  canRejoin,
  onCheckout,
  checkingOut,
  onBack,
}: Props) {
  const price = (priceCents / 100).toFixed(2)
  const symbol = currency.toUpperCase() === 'USD' ? '$' : currency

  const formattedCooldown = cooldownUntil
    ? new Date(cooldownUntil).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : null

  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <div className="max-w-sm w-full bg-zinc-900 border border-zinc-700 rounded-xl p-6 space-y-5">
        <div className="flex items-center gap-2">
          <Hash className="w-5 h-5 text-emerald-500" />
          <h2 className="text-lg font-semibold text-zinc-100">{channelName}</h2>
        </div>

        <div className="text-center py-3">
          <span className="text-3xl font-bold text-emerald-400">
            {symbol}{price}
          </span>
          <span className="text-zinc-400 text-sm ml-1">/month</span>
        </div>

        {inactivityDays != null && inactivityDays > 0 && (
          <div className="flex items-start gap-2 text-sm text-zinc-400">
            <Info className="w-4 h-4 mt-0.5 shrink-0 text-zinc-500" />
            <span>
              Stay active by contributing at least once every {inactivityDays} days
            </span>
          </div>
        )}

        {!canRejoin && formattedCooldown && (
          <div className="flex items-start gap-2 text-sm text-amber-200 bg-amber-900/20 border border-amber-700/30 rounded-lg px-3 py-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-amber-500" />
            <span>You can rejoin after {formattedCooldown}</span>
          </div>
        )}

        <button
          onClick={onCheckout}
          disabled={!canRejoin || checkingOut}
          className="w-full py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {checkingOut && <Loader2 className="w-4 h-4 animate-spin" />}
          {checkingOut ? 'Processing…' : 'Subscribe & Join'}
        </button>

        <button
          onClick={onBack}
          className="w-full text-center text-sm text-zinc-500 hover:text-zinc-400 transition-colors"
        >
          Back
        </button>
      </div>
    </div>
  )
}
