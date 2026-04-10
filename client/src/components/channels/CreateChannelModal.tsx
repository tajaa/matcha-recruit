import { useState } from 'react'
import { X, Loader2, Hash, Globe, Lock, UserPlus, DollarSign } from 'lucide-react'
import { createChannel } from '../../api/channels'
import type { PaidChannelConfig } from '../../api/channels'

interface Props {
  onClose: () => void
  onCreated: (channel: { id: string; name: string; slug: string }) => void
  canCreatePaid?: boolean
}

export default function CreateChannelModal({ onClose, onCreated, canCreatePaid = false }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [visibility, setVisibility] = useState<'public' | 'invite_only' | 'private'>('public')
  const [isPaid, setIsPaid] = useState(false)
  const [priceDollars, setPriceDollars] = useState('')
  const [inactivityDays, setInactivityDays] = useState<number>(14)
  const [warningDays, setWarningDays] = useState<number>(3)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    if (isPaid && (!priceDollars || parseFloat(priceDollars) < 0.5)) {
      setError('Minimum price is $0.50')
      return
    }
    setCreating(true)
    setError('')
    try {
      const paidConfig: PaidChannelConfig | undefined = isPaid ? {
        price_cents: Math.round(parseFloat(priceDollars) * 100),
        inactivity_threshold_days: inactivityDays,
        inactivity_warning_days: warningDays,
      } : undefined
      const ch = await createChannel(name.trim(), description.trim() || undefined, visibility, paidConfig)
      onCreated(ch)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create channel')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-sm mx-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Hash size={18} className="text-emerald-500" />
            <h2 className="text-white font-semibold">New Channel</h2>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-white">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Channel name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. hr-ops, general"
              maxLength={100}
              autoFocus
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Description (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What's this channel for?"
              rows={2}
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600 resize-none"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-400 mb-1.5">Visibility</label>
            <div className="flex gap-2">
              {([
                { value: 'public' as const, icon: Globe, label: 'Public', desc: 'Anyone can join' },
                { value: 'invite_only' as const, icon: UserPlus, label: 'Invite Only', desc: 'Visible, but must be invited' },
                { value: 'private' as const, icon: Lock, label: 'Private', desc: 'Hidden from non-members' },
              ]).map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setVisibility(opt.value)}
                  className={`flex-1 flex flex-col items-center gap-1 px-2 py-2 rounded-lg border text-[11px] transition-colors ${
                    visibility === opt.value
                      ? 'border-emerald-600 bg-emerald-600/10 text-emerald-400'
                      : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
                  }`}
                >
                  <opt.icon size={14} />
                  <span className="font-medium">{opt.label}</span>
                </button>
              ))}
            </div>
          </div>
          {canCreatePaid && <div>
            <label
              className="flex items-center gap-2 cursor-pointer select-none"
              onClick={() => setIsPaid(!isPaid)}
            >
              <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${
                isPaid ? 'bg-emerald-600 border-emerald-600' : 'border-zinc-600 bg-zinc-800'
              }`}>
                {isPaid && <span className="text-white text-[10px] font-bold">✓</span>}
              </div>
              <DollarSign size={14} className={isPaid ? 'text-emerald-400' : 'text-zinc-500'} />
              <span className="text-xs text-zinc-300">Make this a paid channel</span>
            </label>
            {isPaid && (
              <div className="mt-2.5 space-y-2.5 pl-6">
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Monthly price</label>
                  <div className="flex items-center gap-1">
                    <span className="text-zinc-400 text-sm">$</span>
                    <input
                      type="number"
                      min="0.50"
                      step="0.50"
                      value={priceDollars}
                      onChange={(e) => setPriceDollars(e.target.value)}
                      placeholder="9.99"
                      className="w-28 px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Inactivity threshold</label>
                  <select
                    value={inactivityDays}
                    onChange={(e) => setInactivityDays(Number(e.target.value))}
                    className="w-full px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:border-emerald-600"
                  >
                    <option value={7}>7 days</option>
                    <option value={14}>14 days</option>
                    <option value={21}>21 days</option>
                    <option value={30}>30 days</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Warning period</label>
                  <select
                    value={warningDays}
                    onChange={(e) => setWarningDays(Number(e.target.value))}
                    className="w-full px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:outline-none focus:border-emerald-600"
                  >
                    <option value={1}>1 day</option>
                    <option value={2}>2 days</option>
                    <option value={3}>3 days</option>
                    <option value={5}>5 days</option>
                    <option value={7}>7 days</option>
                  </select>
                </div>
                <p className="text-zinc-500 text-[11px] leading-relaxed">
                  Members who don't contribute for {inactivityDays} days will be auto-removed. They can rejoin 1 week after their billing period ends.
                </p>
              </div>
            )}
          </div>}
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <button
            type="submit"
            disabled={creating || !name.trim()}
            className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            {creating ? <Loader2 size={16} className="animate-spin mx-auto" /> : 'Create Channel'}
          </button>
        </form>
      </div>
    </div>
  )
}
