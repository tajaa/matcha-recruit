import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { cancelPersonalSubscription, getMWSubscription, type MWSubscription } from '../../api/matchaWork/billing'

function planName(packId: string | null | undefined): string | null {
  if (packId === 'matcha_work_lite') return 'Lite'
  if (packId === 'matcha_work_personal') return 'Pro'
  return null
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function PersonalPlanCard() {
  const [subscription, setSubscription] = useState<MWSubscription | null>(null)
  const [loading, setLoading] = useState(true)
  const [canceling, setCanceling] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    let mounted = true
    getMWSubscription()
      .then((value) => { if (mounted) setSubscription(value) })
      .catch((cause) => { if (mounted) setError(cause instanceof Error ? cause.message : 'Could not load your plan.') })
      .finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [])

  async function cancel() {
    if (canceling || !window.confirm('Cancel your Espresso plan? You will keep access until the end of the paid period.')) return
    setCanceling(true)
    setError('')
    try {
      const result = await cancelPersonalSubscription()
      setSubscription((current) => current ? { ...current, active: false, status: 'canceled' } : current)
      setNotice(result.message)
      try {
        setSubscription(await getMWSubscription())
      } catch {
        // Cancellation succeeded; a refresh can recover the paid-through date.
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not cancel your plan. Please try again.')
    } finally {
      setCanceling(false)
    }
  }

  const tier = planName(subscription?.pack_id)

  return (
    <section className="mb-8" aria-label="Espresso plan">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-w-dim">Espresso plan</h2>
      <div className="rounded-xl border border-w-line bg-w-surface p-4">
        {loading ? <Loader2 className="animate-spin text-w-dim" size={20} aria-label="Loading plan" /> : (
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="font-medium text-w-text">{tier ? `${tier} plan` : 'No paid plan'}</p>
              {tier && (
                <p className="mt-1 text-sm text-w-dim">
                  {subscription?.status === 'canceled' ? 'Renewal canceled' : 'Renews monthly'}
                  {subscription?.current_period_end && (
                    <> · {subscription.status === 'canceled' ? 'Access until' : 'Next billing'} {formatDate(subscription.current_period_end)}</>
                  )}
                </p>
              )}
              {error && <p role="alert" className="mt-2 text-sm text-red-400">{error}</p>}
              {notice && <p role="status" className="mt-2 text-sm text-w-accent">{notice}</p>}
            </div>
            {tier && subscription?.active && (
              <button
                onClick={() => void cancel()}
                disabled={canceling}
                className="rounded-md px-3 py-1.5 text-sm text-red-400 hover:bg-red-900/20 disabled:opacity-50"
              >
                {canceling ? 'Canceling…' : 'Cancel plan'}
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
