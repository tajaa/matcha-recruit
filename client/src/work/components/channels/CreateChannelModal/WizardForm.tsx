import { useState, useMemo } from 'react'
import {
  X, Loader2, Hash, ChevronRight, ChevronLeft, Check,
} from 'lucide-react'
import { createChannel } from '../../../api/channels'
import type { PaidChannelConfig } from '../../../api/channels'
import type { AccessModel, Props } from './types'
import { STEP_LABELS, getApplicableSteps } from './constants'
import { StepBasics } from './StepBasics'
import { StepAccessModel } from './StepAccessModel'
import { StepPricing } from './StepPricing'
import { StepEngagement } from './StepEngagement'
import { StepReview } from './StepReview'
import { StepManagement } from './StepManagement'

/* ─── Wizard flow ─── */

export function WizardForm({ onClose, onCreated }: Omit<Props, 'canCreatePaid'>) {
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
