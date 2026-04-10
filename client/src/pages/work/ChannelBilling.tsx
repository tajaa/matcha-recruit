import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Hash, Loader2, AlertTriangle, ExternalLink, XCircle, Clock, CreditCard } from 'lucide-react'
import { getMyChannelBilling, getMyPaymentHistory, cancelChannelSubscription } from '../../api/channels'
import type { ChannelSubscription, PaymentEvent } from '../../api/channels'

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  active: { bg: 'bg-emerald-900/30', text: 'text-emerald-400', label: 'Active' },
  past_due: { bg: 'bg-red-900/30', text: 'text-red-400', label: 'Past Due' },
  canceling: { bg: 'bg-amber-900/30', text: 'text-amber-400', label: 'Canceling' },
  canceled: { bg: 'bg-zinc-800', text: 'text-zinc-400', label: 'Canceled' },
}

const EVENT_LABELS: Record<string, string> = {
  subscription_activated: 'Subscribed',
  payment_success: 'Payment',
  payment_failed: 'Payment Failed',
  subscription_canceled: 'Canceled',
  removed_for_inactivity: 'Removed',
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function ChannelBilling() {
  const navigate = useNavigate()
  const [subs, setSubs] = useState<ChannelSubscription[]>([])
  const [history, setHistory] = useState<PaymentEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [cancelingId, setCancelingId] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    Promise.all([getMyChannelBilling(), getMyPaymentHistory()])
      .then(([s, h]) => { setSubs(s); setHistory(h) })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleCancel = async (channelId: string, channelName: string) => {
    if (!window.confirm(`Cancel your subscription to #${channelName}? You'll keep access until the end of the billing period.`)) return
    setCancelingId(channelId)
    try {
      await cancelChannelSubscription(channelId)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to cancel')
    } finally {
      setCancelingId(null)
    }
  }

  const active = subs.filter((s) => !s.removed_for_inactivity)
  const removed = subs.filter((s) => s.removed_for_inactivity)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="animate-spin text-zinc-500" size={24} />
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto px-3 sm:px-6 py-4 sm:py-8">
      <div className="flex items-center gap-3 mb-6">
        <CreditCard size={20} className="text-emerald-500" />
        <h1 className="text-xl font-semibold text-white">Subscriptions & Billing</h1>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-300 text-sm">{error}</div>
      )}

      {subs.length === 0 ? (
        <div className="text-center py-16 text-zinc-500">
          <p>No paid channel subscriptions.</p>
          <button onClick={() => navigate('/work/channels')} className="mt-3 text-emerald-400 hover:text-emerald-300 text-sm">
            Browse channels
          </button>
        </div>
      ) : (
        <>
          {/* Active Subscriptions */}
          {active.length > 0 && (
            <section className="mb-8">
              <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider mb-3">Active Subscriptions</h2>
              <div className="space-y-3">
                {active.map((sub) => {
                  const style = STATUS_STYLES[sub.subscription_status ?? 'canceled'] ?? STATUS_STYLES.canceled
                  return (
                    <div key={sub.channel_id} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <Hash size={16} className="text-emerald-500 shrink-0" />
                            <span className="font-medium text-white truncate">{sub.channel_name}</span>
                            <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${style.bg} ${style.text}`}>
                              {style.label}
                            </span>
                          </div>
                          <div className="flex items-center gap-4 text-sm text-zinc-400 mt-1">
                            <span className="text-emerald-400 font-medium">${(sub.price_cents / 100).toFixed(2)}/mo</span>
                            {sub.paid_through && (
                              <span className="flex items-center gap-1">
                                <Clock size={12} />
                                {sub.subscription_status === 'canceling' ? 'Access until' : 'Next billing'}: {formatDate(sub.paid_through)}
                              </span>
                            )}
                          </div>
                          {sub.days_until_removal != null && (
                            <div className="flex items-center gap-1.5 mt-2 text-xs text-amber-400">
                              <AlertTriangle size={12} />
                              Activity removal in {Math.ceil(sub.days_until_removal)} days — send a message to stay active
                            </div>
                          )}
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <button
                            onClick={() => navigate(`/work/channels/${sub.channel_id}`)}
                            className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 px-2 py-1 rounded hover:bg-zinc-800 transition-colors"
                          >
                            <ExternalLink size={12} />
                            Open
                          </button>
                          {sub.subscription_status === 'active' && (
                            <button
                              onClick={() => handleCancel(sub.channel_id, sub.channel_name)}
                              disabled={cancelingId === sub.channel_id}
                              className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-red-900/20 transition-colors disabled:opacity-50"
                            >
                              {cancelingId === sub.channel_id ? <Loader2 size={12} className="animate-spin" /> : <XCircle size={12} />}
                              Cancel
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {/* Removed Subscriptions */}
          {removed.length > 0 && (
            <section className="mb-8">
              <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider mb-3">Removed for Inactivity</h2>
              <div className="space-y-2">
                {removed.map((sub) => (
                  <div key={sub.channel_id} className="bg-zinc-900/50 border border-zinc-800/50 rounded-lg p-3 flex items-center gap-3">
                    <Hash size={14} className="text-zinc-600 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <span className="text-sm text-zinc-400">{sub.channel_name}</span>
                      {sub.cooldown_until && (
                        <p className="text-xs text-zinc-600">Can rejoin after {formatDate(sub.cooldown_until)}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Payment History */}
          {history.length > 0 && (
            <section>
              <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider mb-3">Payment History</h2>
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
                <div className="divide-y divide-zinc-800">
                  {history.map((evt, i) => (
                    <div key={i} className="flex items-center gap-4 px-4 py-3 text-sm">
                      <span className="text-zinc-300 w-32 shrink-0">{EVENT_LABELS[evt.event_type] ?? evt.event_type}</span>
                      <span className="flex-1 text-zinc-500 truncate flex items-center gap-1.5">
                        <Hash size={12} className="shrink-0" />
                        {evt.channel_name}
                      </span>
                      <span className="text-zinc-300 w-20 text-right shrink-0">
                        {evt.amount_cents > 0 ? `$${(evt.amount_cents / 100).toFixed(2)}` : '—'}
                      </span>
                      <span className="text-zinc-600 w-28 text-right shrink-0">{formatDate(evt.created_at)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
