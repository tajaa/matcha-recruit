import { useState } from 'react'
import { Hash, Users, Loader2, ArrowRight, ArrowLeft, Check, CreditCard, Clock, MessageSquare, Shield, Zap } from 'lucide-react'

interface Props {
  channelName: string
  channelDescription: string | null
  memberCount: number
  priceCents: number
  currency: string
  inactivityDays: number | null
  cooldownUntil: string | null
  canRejoin: boolean
  onJoin: () => void
  joining: boolean
  onBack: () => void
}

const STEPS = ['Preview', 'Details', 'Confirm'] as const

export default function PaidChannelJoinWizard({
  channelName,
  channelDescription,
  memberCount,
  priceCents,
  currency,
  inactivityDays,
  cooldownUntil,
  canRejoin,
  onJoin,
  joining,
  onBack,
}: Props) {
  const [step, setStep] = useState(0)

  const price = (priceCents / 100).toFixed(2)
  const symbol = currency.toUpperCase() === 'USD' ? '$' : currency.toUpperCase()

  const formattedCooldown = cooldownUntil
    ? new Date(cooldownUntil).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : null

  return (
    <div className="flex items-center justify-center h-full p-4">
      <div className="max-w-lg w-full bg-zinc-900 border border-zinc-700 rounded-xl overflow-hidden">
        {/* Step indicator */}
        <div className="flex items-center border-b border-zinc-800 px-6 py-3">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center flex-1">
              <div className="flex items-center gap-2">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 transition-colors ${
                    i < step
                      ? 'bg-emerald-600 text-white'
                      : i === step
                        ? 'bg-emerald-600/20 text-emerald-400 ring-1 ring-emerald-600'
                        : 'bg-zinc-800 text-zinc-500'
                  }`}
                >
                  {i < step ? <Check size={12} /> : i + 1}
                </div>
                <span
                  className={`text-xs font-medium hidden sm:block ${
                    i === step ? 'text-zinc-200' : 'text-zinc-500'
                  }`}
                >
                  {label}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div
                  className={`flex-1 h-px mx-3 ${
                    i < step ? 'bg-emerald-600/40' : 'bg-zinc-800'
                  }`}
                />
              )}
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="p-6">
          {step === 0 && (
            <StepPreview
              channelName={channelName}
              channelDescription={channelDescription}
              memberCount={memberCount}
              price={price}
              symbol={symbol}
            />
          )}
          {step === 1 && (
            <StepDetails
              price={price}
              symbol={symbol}
              inactivityDays={inactivityDays}
            />
          )}
          {step === 2 && (
            <StepConfirm
              channelName={channelName}
              price={price}
              symbol={symbol}
              inactivityDays={inactivityDays}
              cooldownUntil={formattedCooldown}
              canRejoin={canRejoin}
            />
          )}
        </div>

        {/* Footer navigation */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-zinc-800">
          <button
            onClick={step === 0 ? onBack : () => setStep(step - 1)}
            disabled={joining}
            className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-50"
          >
            <ArrowLeft size={14} />
            {step === 0 ? 'Back' : 'Previous'}
          </button>

          {step < 2 ? (
            <button
              onClick={() => setStep(step + 1)}
              className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Next
              <ArrowRight size={14} />
            </button>
          ) : (
            <button
              onClick={onJoin}
              disabled={!canRejoin || joining}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {joining ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Joining...
                </>
              ) : (
                <>
                  Join Beta — {symbol}{price}/mo
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── Step 1: Channel Preview ──────────────────────────── */

function StepPreview({
  channelName,
  channelDescription,
  memberCount,
  price,
  symbol,
}: {
  channelName: string
  channelDescription: string | null
  memberCount: number
  price: string
  symbol: string
}) {
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-emerald-600/15 flex items-center justify-center">
          <Hash size={20} className="text-emerald-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-zinc-100">{channelName}</h2>
          <span className="text-xs text-emerald-400 font-medium">Premium Channel</span>
        </div>
      </div>

      {channelDescription && (
        <p className="text-sm text-zinc-400 leading-relaxed">{channelDescription}</p>
      )}

      <div className="text-sm text-zinc-400">
        This is a premium channel requiring a monthly subscription.
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
          <div className="flex items-center gap-2 text-zinc-500 mb-1">
            <Users size={13} />
            <span className="text-xs">Members</span>
          </div>
          <p className="text-lg font-semibold text-zinc-200">{memberCount}</p>
        </div>
        <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-3">
          <div className="flex items-center gap-2 text-zinc-500 mb-1">
            <CreditCard size={13} />
            <span className="text-xs">Monthly</span>
          </div>
          <p className="text-lg font-semibold text-emerald-400">{symbol}{price}</p>
        </div>
      </div>

      <div className="space-y-2.5">
        <p className="text-xs font-medium text-zinc-500 uppercase tracking-wide">What you get</p>
        <div className="space-y-2">
          <BenefitRow icon={<MessageSquare size={14} />} text="Full access to channel messages and history" />
          <BenefitRow icon={<Users size={14} />} text="Connect with the community and contributors" />
          <BenefitRow icon={<Zap size={14} />} text="Participate in discussions and share content" />
        </div>
      </div>
    </div>
  )
}

function BenefitRow({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-2.5 text-sm text-zinc-300">
      <span className="text-emerald-500 shrink-0">{icon}</span>
      {text}
    </div>
  )
}

/* ── Step 2: Subscription Details ─────────────────────── */

function StepDetails({
  price,
  symbol,
  inactivityDays,
}: {
  price: string
  symbol: string
  inactivityDays: number | null
}) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-zinc-100">Subscription details</h2>
        <p className="text-sm text-zinc-500 mt-1">Review before subscribing</p>
      </div>

      <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-zinc-400">Billing cycle</span>
          <span className="text-sm text-zinc-200 font-medium">Monthly</span>
        </div>
        <div className="h-px bg-zinc-700/50" />
        <div className="flex items-center justify-between">
          <span className="text-sm text-zinc-400">Price</span>
          <span className="text-sm text-emerald-400 font-semibold">{symbol}{price}/month</span>
        </div>
        <div className="h-px bg-zinc-700/50" />
        <div className="flex items-center justify-between">
          <span className="text-sm text-zinc-400">Payment</span>
          <span className="text-sm text-zinc-200">Stripe (beta)</span>
        </div>
      </div>

      {inactivityDays != null && inactivityDays > 0 && (
        <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2 text-zinc-200 font-medium text-sm">
            <Clock size={15} className="text-amber-400" />
            Engagement required
          </div>
          <p className="text-sm text-zinc-400 leading-relaxed">
            You'll need to contribute regularly to maintain access. Members who
            haven't posted in <span className="text-zinc-200 font-medium">{inactivityDays} days</span> may
            be removed from the channel.
          </p>
          <p className="text-xs text-zinc-500">
            Contributions include sending messages and sharing files.
          </p>
        </div>
      )}

      <div className="flex items-start gap-2.5 text-xs text-zinc-500">
        <Shield size={14} className="shrink-0 mt-0.5 text-zinc-600" />
        <span>
          Your subscription can be cancelled at any time from the billing page.
          You'll retain access until the end of your current billing period.
        </span>
      </div>
    </div>
  )
}

/* ── Step 3: Confirm & Subscribe ──────────────────────── */

function StepConfirm({
  channelName,
  price,
  symbol,
  inactivityDays,
  cooldownUntil,
  canRejoin,
}: {
  channelName: string
  price: string
  symbol: string
  inactivityDays: number | null
  cooldownUntil: string | null
  canRejoin: boolean
}) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold text-zinc-100">Confirm subscription</h2>
        <p className="text-sm text-zinc-500 mt-1">You're about to join a premium channel</p>
      </div>

      <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-zinc-400">Channel</span>
          <span className="text-sm text-zinc-200 font-medium flex items-center gap-1.5">
            <Hash size={12} className="text-emerald-500" />
            {channelName}
          </span>
        </div>
        <div className="h-px bg-zinc-700/50" />
        <div className="flex items-center justify-between">
          <span className="text-sm text-zinc-400">Amount</span>
          <span className="text-sm text-emerald-400 font-semibold">{symbol}{price}/month</span>
        </div>
        {inactivityDays != null && inactivityDays > 0 && (
          <>
            <div className="h-px bg-zinc-700/50" />
            <div className="flex items-center justify-between">
              <span className="text-sm text-zinc-400">Activity requirement</span>
              <span className="text-sm text-zinc-200">Post every {inactivityDays} days</span>
            </div>
          </>
        )}
      </div>

      {!canRejoin && cooldownUntil && (
        <div className="flex items-start gap-2.5 text-sm text-amber-200 bg-amber-900/20 border border-amber-700/30 rounded-lg px-4 py-3">
          <Clock size={15} className="shrink-0 mt-0.5 text-amber-400" />
          <span>
            You can rejoin this channel after <span className="font-medium">{cooldownUntil}</span>.
          </span>
        </div>
      )}

      <p className="text-xs text-zinc-600 text-center">
        Beta pricing. Payment processing via Stripe will be enabled soon.
      </p>
    </div>
  )
}
