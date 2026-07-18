import { Hash, Loader2, LogIn } from 'lucide-react'
import type { ChannelDetail, ChannelPaymentInfo } from '../../api/channels'
import PaidChannelJoinWizard from '../../components/channels/PaidChannelJoinWizard'

export function ChannelLoading() {
  return (
    <div className="flex items-center justify-center h-full">
      <Loader2 className="animate-spin text-w-dim" size={24} />
    </div>
  )
}

interface ChannelJoinGateProps {
  channel: ChannelDetail | null
  paymentInfo: ChannelPaymentInfo | null
  joining: boolean
  onJoin: () => void
  onBack: () => void
  brand: string
}

// Not a member — show join prompt or invite-only message
export function ChannelJoinGate({
  channel,
  paymentInfo,
  joining,
  onJoin,
  onBack,
  brand,
}: ChannelJoinGateProps) {
  // Paid channel — show payment gate
  if (paymentInfo?.is_paid) {
    return (
      <PaidChannelJoinWizard
        channelName={channel?.name ?? 'Channel'}
        channelDescription={channel?.description ?? null}
        memberCount={channel?.member_count ?? 0}
        priceCents={paymentInfo.price_cents ?? 0}
        currency={paymentInfo.currency ?? 'usd'}
        inactivityDays={paymentInfo.inactivity_threshold_days ?? null}
        cooldownUntil={paymentInfo.cooldown_until ?? null}
        canRejoin={paymentInfo.can_rejoin ?? true}
        onJoin={onJoin}
        joining={joining}
        onBack={onBack}
      />
    )
  }
  // Free channel — existing join prompt
  const isPublic = !channel?.visibility || channel.visibility === 'public'
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4">
      <Hash size={48} className="text-w-faint" />
      <p className="text-w-dim text-sm">
        {isPublic ? "You're not a member of this channel" : "This channel requires an invitation to join"}
      </p>
      {isPublic && (
        <button
          onClick={onJoin}
          disabled={joining}
          className="flex items-center gap-2 px-4 py-2 bg-w-accent hover:bg-w-accent-hi text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
        >
          {joining ? <Loader2 size={14} className="animate-spin" /> : <LogIn size={14} />}
          Join Channel
        </button>
      )}
      <button onClick={onBack} className="text-w-dim text-xs hover:text-w-text">
        Back to {brand}
      </button>
    </div>
  )
}

interface ChannelErrorGateProps {
  error: string
  onBack: () => void
  brand: string
}

export function ChannelErrorGate({ error, onBack, brand }: ChannelErrorGateProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4">
      <p className="text-red-400 text-sm">{error}</p>
      <button onClick={onBack} className="text-w-dim text-xs hover:text-w-text">
        Back to {brand}
      </button>
    </div>
  )
}
