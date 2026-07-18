import { Hash } from 'lucide-react'
import type { AccessModel } from './types'

/* ─── Step 5: Review ─── */

export function StepReview({
  name, description, visibility, accessModel, priceDollars, inactivityDays, warningDays,
}: {
  name: string
  description: string
  visibility: string
  accessModel: AccessModel
  priceDollars: string
  inactivityDays: number
  warningDays: number
}) {
  const visibilityLabel =
    visibility === 'public' ? 'Public' : visibility === 'invite_only' ? 'Invite Only' : 'Private'

  const accessLabel =
    accessModel === 'free' ? 'Free' : accessModel === 'paid' ? 'Paid Subscription' : 'Paid + Engagement'

  return (
    <div className="space-y-3">
      <p className="text-xs text-zinc-400 mb-1">Review your channel settings before creating.</p>

      <div className="bg-zinc-800/70 rounded-lg border border-zinc-700/50 divide-y divide-zinc-700/50">
        <div className="px-4 py-3">
          <div className="flex items-center gap-2 mb-1">
            <Hash size={14} className="text-emerald-500" />
            <span className="text-white font-medium text-sm">{name}</span>
          </div>
          {description && (
            <p className="text-xs text-zinc-400 ml-[22px]">{description}</p>
          )}
        </div>

        <div className="px-4 py-2.5 flex items-center justify-between">
          <span className="text-xs text-zinc-500">Visibility</span>
          <span className="text-xs text-zinc-300">{visibilityLabel}</span>
        </div>

        <div className="px-4 py-2.5 flex items-center justify-between">
          <span className="text-xs text-zinc-500">Access</span>
          <span className="text-xs text-zinc-300">{accessLabel}</span>
        </div>

        {accessModel !== 'free' && (
          <div className="px-4 py-2.5 flex items-center justify-between">
            <span className="text-xs text-zinc-500">Price</span>
            <span className="text-xs text-emerald-400 font-medium">${parseFloat(priceDollars).toFixed(2)}/mo</span>
          </div>
        )}

        {accessModel === 'paid_engagement' && (
          <>
            <div className="px-4 py-2.5 flex items-center justify-between">
              <span className="text-xs text-zinc-500">Inactivity threshold</span>
              <span className="text-xs text-zinc-300">{inactivityDays} days</span>
            </div>
            <div className="px-4 py-2.5 flex items-center justify-between">
              <span className="text-xs text-zinc-500">Warning period</span>
              <span className="text-xs text-zinc-300">{warningDays} days</span>
            </div>
          </>
        )}
      </div>

      {accessModel !== 'free' && (
        <p className="text-[11px] text-zinc-500 leading-relaxed">
          Stripe handles billing. Subscription revenue is held by the platform until creator payouts ship. Members can cancel anytime from their billing page.
        </p>
      )}
    </div>
  )
}
