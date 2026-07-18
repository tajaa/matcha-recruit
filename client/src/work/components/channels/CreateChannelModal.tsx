import { useState, useMemo } from 'react'
import {
  X, Loader2, Hash, Globe, Lock, UserPlus, DollarSign,
  ChevronRight, ChevronLeft, Check, Zap, Users, Shield,
  Clock, AlertTriangle,
} from 'lucide-react'
import { createChannel } from '../../api/channels'
import type { PaidChannelConfig } from '../../api/channels'

interface Props {
  onClose: () => void
  onCreated: (channel: { id: string; name: string; slug: string }) => void
  canCreatePaid?: boolean
}

type AccessModel = 'free' | 'paid' | 'paid_engagement'

const STEP_LABELS: Record<number, string> = {
  1: 'Basics',
  2: 'Access Model',
  3: 'Pricing',
  4: 'Engagement',
  5: 'Review',
  6: 'Management',
}

const PRICE_SUGGESTIONS = [5, 10, 15, 25, 50]

const INACTIVITY_OPTIONS = [
  { value: 7, label: '7 days' },
  { value: 14, label: '14 days' },
  { value: 21, label: '21 days' },
  { value: 30, label: '30 days' },
]

const WARNING_OPTIONS = [
  { value: 1, label: '1 day' },
  { value: 2, label: '2 days' },
  { value: 3, label: '3 days' },
  { value: 5, label: '5 days' },
  { value: 7, label: '7 days' },
]

function getApplicableSteps(accessModel: AccessModel): number[] {
  switch (accessModel) {
    case 'free':
      return [1, 2, 5]
    case 'paid':
      return [1, 2, 3, 5, 6]
    case 'paid_engagement':
      return [1, 2, 3, 4, 5, 6]
  }
}

/* ─── Simple (non-wizard) flow ─── */

function SimpleForm({ onClose, onCreated }: Omit<Props, 'canCreatePaid'>) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [visibility, setVisibility] = useState<'public' | 'invite_only' | 'private'>('public')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    setError('')
    try {
      const ch = await createChannel(name.trim(), description.trim() || undefined, visibility)
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
                { value: 'public' as const, icon: Globe, label: 'Public', desc: 'Listed; anyone can join' },
                { value: 'invite_only' as const, icon: UserPlus, label: 'Invite Only', desc: 'Listed; invite required' },
                { value: 'private' as const, icon: Lock, label: 'Private', desc: 'Hidden; invite required' },
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
                  <span className="text-[9px] opacity-70 leading-tight text-center">{opt.desc}</span>
                </button>
              ))}
            </div>
          </div>
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

/* ─── Wizard flow ─── */

function WizardForm({ onClose, onCreated }: Omit<Props, 'canCreatePaid'>) {
  // Step state
  const [stepIndex, setStepIndex] = useState(0)

  // Step 1: Basics
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [visibility, setVisibility] = useState<'public' | 'invite_only' | 'private'>('public')

  // Step 2: Access model
  const [accessModel, setAccessModel] = useState<AccessModel>('free')

  // Step 3: Pricing
  const [priceDollars, setPriceDollars] = useState('')

  // Step 4: Engagement
  const [inactivityDays, setInactivityDays] = useState(14)
  const [warningDays, setWarningDays] = useState(3)

  // Submission
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  const steps = useMemo(() => getApplicableSteps(accessModel), [accessModel])
  const currentStep = steps[stepIndex]
  const isFirst = stepIndex === 0
  const isLast = stepIndex === steps.length - 1

  function canProceed(): boolean {
    switch (currentStep) {
      case 1: return name.trim().length > 0
      case 2: return true
      case 3: return priceDollars !== '' && parseFloat(priceDollars) >= 0.5
      case 4: return true
      case 5: return true
      case 6: return true
      default: return false
    }
  }

  function goNext() {
    if (!canProceed()) return
    if (isLast) return
    setError('')
    setStepIndex((i) => Math.min(i + 1, steps.length - 1))
  }

  function goBack() {
    if (isFirst) return
    setError('')
    setStepIndex((i) => Math.max(i - 1, 0))
  }

  async function handleCreate() {
    if (!name.trim()) return
    setCreating(true)
    setError('')
    try {
      let paidConfig: PaidChannelConfig | undefined
      if (accessModel === 'paid') {
        paidConfig = {
          price_cents: Math.round(parseFloat(priceDollars) * 100),
          inactivity_threshold_days: null,
        }
      } else if (accessModel === 'paid_engagement') {
        paidConfig = {
          price_cents: Math.round(parseFloat(priceDollars) * 100),
          inactivity_threshold_days: inactivityDays,
          inactivity_warning_days: warningDays,
        }
      }
      const ch = await createChannel(name.trim(), description.trim() || undefined, visibility, paidConfig)
      onCreated(ch)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create channel')
    } finally {
      setCreating(false)
    }
  }

  // Progress bar
  const progress = ((stepIndex + 1) / steps.length) * 100

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-md mx-4 overflow-hidden">
        {/* Progress bar */}
        <div className="h-1 bg-zinc-800">
          <div
            className="h-full bg-emerald-500 transition-all duration-300 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-3">
          <div className="flex items-center gap-2">
            <Hash size={18} className="text-emerald-500" />
            <h2 className="text-white font-semibold">New Channel</h2>
            <span className="text-xs text-zinc-500 ml-1">
              Step {stepIndex + 1} of {steps.length} &middot; {STEP_LABELS[currentStep]}
            </span>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-white transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Step content */}
        <div className="px-6 pb-2 min-h-[260px]">
          {currentStep === 1 && (
            <StepBasics
              name={name}
              setName={setName}
              description={description}
              setDescription={setDescription}
              visibility={visibility}
              setVisibility={setVisibility}
            />
          )}
          {currentStep === 2 && (
            <StepAccessModel
              accessModel={accessModel}
              setAccessModel={setAccessModel}
            />
          )}
          {currentStep === 3 && (
            <StepPricing
              priceDollars={priceDollars}
              setPriceDollars={setPriceDollars}
            />
          )}
          {currentStep === 4 && (
            <StepEngagement
              inactivityDays={inactivityDays}
              setInactivityDays={setInactivityDays}
              warningDays={warningDays}
              setWarningDays={setWarningDays}
            />
          )}
          {currentStep === 5 && (
            <StepReview
              name={name}
              description={description}
              visibility={visibility}
              accessModel={accessModel}
              priceDollars={priceDollars}
              inactivityDays={inactivityDays}
              warningDays={warningDays}
            />
          )}
          {currentStep === 6 && (
            <StepManagement accessModel={accessModel} inactivityDays={inactivityDays} />
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="px-6 pb-2">
            <p className="text-red-400 text-xs">{error}</p>
          </div>
        )}

        {/* Footer buttons */}
        <div className="flex items-center justify-between px-6 pb-5 pt-2">
          <button
            type="button"
            onClick={isFirst ? onClose : goBack}
            className="flex items-center gap-1 px-3 py-2 text-sm text-zinc-400 hover:text-white transition-colors rounded-lg hover:bg-zinc-800"
          >
            {isFirst ? (
              'Cancel'
            ) : (
              <>
                <ChevronLeft size={14} />
                Back
              </>
            )}
          </button>

          {isLast ? (
            <button
              type="button"
              onClick={handleCreate}
              disabled={creating}
              className="flex items-center gap-1.5 px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
            >
              {creating ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Check size={14} />
              )}
              {creating ? 'Creating...' : 'Create Channel'}
            </button>
          ) : (
            <button
              type="button"
              onClick={goNext}
              disabled={!canProceed()}
              className="flex items-center gap-1 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
            >
              Next
              <ChevronRight size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/* ─── Step 1: Basics ─── */

function StepBasics({
  name, setName, description, setDescription, visibility, setVisibility,
}: {
  name: string
  setName: (v: string) => void
  description: string
  setDescription: (v: string) => void
  visibility: 'public' | 'invite_only' | 'private'
  setVisibility: (v: 'public' | 'invite_only' | 'private') => void
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs text-zinc-400 mb-1">Channel name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. premium-insights, coaching-circle"
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
          placeholder="What's this channel about?"
          rows={2}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600 resize-none"
        />
      </div>
      <div>
        <label className="block text-xs text-zinc-400 mb-1.5">Visibility</label>
        <div className="flex gap-2">
          {([
            { value: 'public' as const, icon: Globe, label: 'Public', desc: 'Listed; anyone can join' },
            { value: 'invite_only' as const, icon: UserPlus, label: 'Invite Only', desc: 'Listed; invite required' },
            { value: 'private' as const, icon: Lock, label: 'Private', desc: 'Hidden; invite required' },
          ]).map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setVisibility(opt.value)}
              className={`flex-1 flex flex-col items-center gap-1 px-2 py-2.5 rounded-lg border text-[11px] transition-colors ${
                visibility === opt.value
                  ? 'border-emerald-600 bg-emerald-600/10 text-emerald-400'
                  : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
              }`}
            >
              <opt.icon size={14} />
              <span className="font-medium">{opt.label}</span>
              <span className="text-[9px] opacity-70 leading-tight text-center">{opt.desc}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ─── Step 2: Access Model ─── */

function StepAccessModel({
  accessModel, setAccessModel,
}: {
  accessModel: AccessModel
  setAccessModel: (v: AccessModel) => void
}) {
  const models: {
    value: AccessModel
    icon: typeof Globe
    title: string
    description: string
    badge?: string
  }[] = [
    {
      value: 'free',
      icon: Users,
      title: 'Free',
      description: 'Anyone can join and participate. Great for community channels and open discussions.',
    },
    {
      value: 'paid',
      icon: DollarSign,
      title: 'Paid Subscription',
      description: 'Members pay a monthly fee to access the channel. No activity requirements.',
      badge: 'Recurring',
    },
    {
      value: 'paid_engagement',
      icon: Zap,
      title: 'Paid + Engagement',
      description: 'Monthly fee with activity requirements. Inactive members are auto-removed to keep the community engaged.',
      badge: 'Active',
    },
  ]

  return (
    <div className="space-y-2.5">
      <p className="text-xs text-zinc-400 mb-3">How should members access this channel?</p>
      {models.map((m) => (
        <button
          key={m.value}
          type="button"
          onClick={() => setAccessModel(m.value)}
          className={`w-full text-left p-3.5 rounded-lg border transition-all ${
            accessModel === m.value
              ? 'border-emerald-600 bg-emerald-600/10'
              : 'border-zinc-700 bg-zinc-800/50 hover:border-zinc-600'
          }`}
        >
          <div className="flex items-start gap-3">
            <div className={`mt-0.5 p-1.5 rounded-md ${
              accessModel === m.value ? 'bg-emerald-600/20 text-emerald-400' : 'bg-zinc-700/50 text-zinc-400'
            }`}>
              <m.icon size={16} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className={`text-sm font-medium ${
                  accessModel === m.value ? 'text-emerald-400' : 'text-zinc-200'
                }`}>{m.title}</span>
                {m.badge && (
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                    accessModel === m.value
                      ? 'bg-emerald-600/20 text-emerald-400'
                      : 'bg-zinc-700 text-zinc-400'
                  }`}>{m.badge}</span>
                )}
              </div>
              <p className="text-xs text-zinc-500 mt-0.5 leading-relaxed">{m.description}</p>
            </div>
            <div className={`mt-1 w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
              accessModel === m.value
                ? 'border-emerald-500 bg-emerald-500'
                : 'border-zinc-600'
            }`}>
              {accessModel === m.value && <Check size={10} className="text-white" />}
            </div>
          </div>
        </button>
      ))}
    </div>
  )
}

/* ─── Step 3: Pricing ─── */

function StepPricing({
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

/* ─── Step 4: Engagement Rules ─── */

function StepEngagement({
  inactivityDays, setInactivityDays, warningDays, setWarningDays,
}: {
  inactivityDays: number
  setInactivityDays: (v: number) => void
  warningDays: number
  setWarningDays: (v: number) => void
}) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-zinc-400 mb-2">
          <Clock size={12} className="inline mr-1 -mt-0.5" />
          Inactivity threshold
        </label>
        <p className="text-[11px] text-zinc-500 mb-2">How long before a member is considered inactive?</p>
        <div className="flex flex-wrap gap-2">
          {INACTIVITY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setInactivityDays(opt.value)}
              className={`px-3 py-1.5 rounded-lg border text-sm transition-colors ${
                inactivityDays === opt.value
                  ? 'border-emerald-600 bg-emerald-600/10 text-emerald-400 font-medium'
                  : 'border-zinc-700 bg-zinc-800 text-zinc-300 hover:border-zinc-600'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-xs text-zinc-400 mb-2">
          <AlertTriangle size={12} className="inline mr-1 -mt-0.5" />
          Warning period
        </label>
        <p className="text-[11px] text-zinc-500 mb-2">How much notice before removal?</p>
        <div className="flex flex-wrap gap-2">
          {WARNING_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setWarningDays(opt.value)}
              className={`px-3 py-1.5 rounded-lg border text-sm transition-colors ${
                warningDays === opt.value
                  ? 'border-emerald-600 bg-emerald-600/10 text-emerald-400 font-medium'
                  : 'border-zinc-700 bg-zinc-800 text-zinc-300 hover:border-zinc-600'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="p-3 bg-zinc-800/50 rounded-lg border border-zinc-700/50">
        <p className="text-xs text-zinc-300 leading-relaxed">
          Members who don't contribute for <span className="text-emerald-400 font-medium">{inactivityDays} days</span> get
          a <span className="text-emerald-400 font-medium">{warningDays}-day warning</span>, then are auto-removed.
          They can rejoin after their billing period ends.
        </p>
      </div>
    </div>
  )
}

/* ─── Step 5: Review ─── */

function StepReview({
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

/* ─── Step 6: Management Guide ─── */

function StepManagement({ accessModel, inactivityDays }: { accessModel: AccessModel; inactivityDays: number }) {
  const guides = [
    {
      icon: <Users size={16} className="text-emerald-400" />,
      title: 'Member Management',
      desc: 'View all subscribers in the channel member list. Promote trusted members to moderators who can help manage content.',
    },
    {
      icon: <DollarSign size={16} className="text-emerald-400" />,
      title: 'Revenue Dashboard',
      desc: 'Click the Settings gear icon in your channel header to see subscriber count, monthly recurring revenue, and total earnings.',
    },
    {
      icon: <Shield size={16} className="text-emerald-400" />,
      title: 'Invite Links',
      desc: 'Generate shareable invite links from the channel header. Each link can be set to expire or be single-use for controlled access.',
    },
    ...(accessModel === 'paid_engagement' ? [{
      icon: <Clock size={16} className="text-amber-400" />,
      title: 'Inactivity Auto-Removal',
      desc: `Members who don't contribute for ${inactivityDays} days receive a warning banner. After the warning period, they're auto-removed. They can rejoin once their current billing period ends.`,
    }] : []),
    {
      icon: <AlertTriangle size={16} className="text-amber-400" />,
      title: 'Failed Payments',
      desc: 'If a subscriber\'s payment fails, their status changes to "past due." They keep access until the end of their billing period, then lose it automatically.',
    },
    {
      icon: <Zap size={16} className="text-emerald-400" />,
      title: 'Tips & Gifts',
      desc: 'Subscribers can send you one-time tips from within the channel. Tip amounts appear in your revenue dashboard for visibility — funds are held by the platform until creator payouts ship.',
    },
  ]

  return (
    <div className="space-y-3">
      <p className="text-xs text-zinc-400 mb-1">Here's how to manage your paid channel after creation.</p>
      <div className="space-y-2 max-h-[280px] overflow-y-auto pr-1">
        {guides.map((g) => (
          <div key={g.title} className="flex gap-3 p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/40">
            <div className="mt-0.5 shrink-0">{g.icon}</div>
            <div>
              <p className="text-xs font-medium text-zinc-200">{g.title}</p>
              <p className="text-[11px] text-zinc-500 leading-relaxed mt-0.5">{g.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ─── Main export ─── */

export default function CreateChannelModal({ onClose, onCreated, canCreatePaid = false }: Props) {
  if (canCreatePaid) {
    return <WizardForm onClose={onClose} onCreated={onCreated} />
  }
  return <SimpleForm onClose={onClose} onCreated={onCreated} />
}
