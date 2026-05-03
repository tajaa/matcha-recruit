import { useState } from 'react'
import { Heart, X, Loader2 } from 'lucide-react'
import { sendChannelTip } from '../../api/channels'

interface Props {
  channelId: string
  channelName: string
  onClose: () => void
}

const PRESETS = [100, 300, 500, 1000, 2500]

export default function TipModal({ channelId, channelName, onClose }: Props) {
  const [amountCents, setAmountCents] = useState(500)
  const [customDollars, setCustomDollars] = useState('')
  const [useCustom, setUseCustom] = useState(false)
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  const effectiveAmount = useCustom ? Math.round(parseFloat(customDollars || '0') * 100) : amountCents
  const isValid = effectiveAmount >= 100 && effectiveAmount <= 50000

  async function handleSend() {
    if (!isValid) return
    setSending(true)
    setError('')
    try {
      const { checkout_url } = await sendChannelTip(channelId, effectiveAmount, message || undefined)
      window.location.href = checkout_url
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create checkout')
      setSending(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-sm mx-4 p-5"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Heart size={18} className="text-pink-400" />
            <h3 className="text-white font-semibold">Send a tip</h3>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
            <X size={18} />
          </button>
        </div>

        <p className="text-xs text-zinc-500 mb-4">
          Show appreciation to the creator of <span className="text-zinc-300">#{channelName}</span>
        </p>
        <p className="text-[10px] text-zinc-600 leading-relaxed mb-3">
          Tips are held by the platform until creator payouts ship. The creator will see the amount and your message.
        </p>

        {/* Preset amounts */}
        <div className="flex flex-wrap gap-2 mb-3">
          {PRESETS.map((cents) => (
            <button
              key={cents}
              onClick={() => { setAmountCents(cents); setUseCustom(false) }}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                !useCustom && amountCents === cents
                  ? 'bg-emerald-600 text-white'
                  : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200'
              }`}
            >
              ${cents / 100}
            </button>
          ))}
        </div>

        {/* Custom amount */}
        <div className="mb-4">
          <div className="flex items-center gap-2">
            <span className="text-zinc-500 text-sm">$</span>
            <input
              type="number"
              min="1"
              max="500"
              step="0.01"
              placeholder="Custom amount"
              value={customDollars}
              onChange={(e) => { setCustomDollars(e.target.value); setUseCustom(true) }}
              onFocus={() => setUseCustom(true)}
              className="flex-1 px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm placeholder:text-zinc-600 focus:outline-none focus:border-emerald-600"
            />
          </div>
          {useCustom && customDollars && !isValid && (
            <p className="text-xs text-red-400 mt-1">Amount must be between $1.00 and $500.00</p>
          )}
        </div>

        {/* Message */}
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value.slice(0, 200))}
          placeholder="Say thanks..."
          rows={2}
          maxLength={200}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm placeholder:text-zinc-600 focus:outline-none focus:border-emerald-600 resize-none mb-1"
        />
        <p className="text-[10px] text-zinc-600 text-right mb-4">{message.length}/200</p>

        {error && <p className="text-xs text-red-400 mb-3">{error}</p>}

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={!isValid || sending}
          className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {sending ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <>
              <Heart size={14} />
              Send ${(effectiveAmount / 100).toFixed(2)} Tip
            </>
          )}
        </button>
      </div>
    </div>
  )
}
