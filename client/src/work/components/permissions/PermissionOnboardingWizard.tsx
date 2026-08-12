import { useState } from 'react'
import { ArrowRight, Check, ChevronLeft, ChevronRight, Play, Shield, Sparkles, UserRound, X } from 'lucide-react'
import { ACCESS_LEVEL_COPY, ACCESS_LEVELS } from '../../utils/workAccess'

export const WORK_ACCESS_WIZARD_DISMISSED_KEY = 'mw-work-access-wizard-dismissed'

interface Props {
  onClose: () => void
  onReview: () => void
}

const steps = [
  {
    title: 'Access is separate from collaboration',
    description: 'Inviting someone to a thread lets them collaborate. Workspace access decides what they can review, approve, and execute through Huume and Ops.',
    icon: Sparkles,
  },
  {
    title: 'Start with the defaults',
    description: 'Company employees start as Members. Company clients start as Operators. External collaborators start as Guests. Company owners and platform admins are Admins.',
    icon: UserRound,
  },
  {
    title: 'Use the smallest level that fits',
    description: 'Reviewer is for sensitive visibility. Operator is for trusted people who can run approved work. Admin is reserved for workspace management.',
    icon: Shield,
  },
  {
    title: 'Huume always stages before it runs',
    description: 'Members can prepare an action. Operators approve and execute it on a later turn. This separation keeps drafts reviewable and execution intentional.',
    icon: Play,
  },
]

export default function PermissionOnboardingWizard({ onClose, onReview }: Props) {
  const [step, setStep] = useState(0)
  const isLast = step === steps.length - 1
  const current = steps[step]
  const Icon = current.icon

  function finish(review: boolean) {
    try { localStorage.setItem(WORK_ACCESS_WIZARD_DISMISSED_KEY, '1') } catch { /* best effort */ }
    if (review) onReview()
    else onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
      <div className="w-full max-w-xl overflow-hidden rounded-2xl border border-w-line bg-w-surface shadow-2xl">
        <div className="flex items-center justify-between border-b border-w-line px-6 py-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-w-accent">Workspace access</p>
            <p className="mt-1 text-sm text-w-dim">A short guide for Huume authority</p>
          </div>
          <button type="button" onClick={() => finish(false)} className="rounded-md p-1.5 text-w-faint hover:bg-w-surface2 hover:text-w-text" aria-label="Close">
            <X size={17} />
          </button>
        </div>

        <div className="flex gap-1.5 px-6 pt-5">
          {steps.map((_, index) => <span key={index} className={`h-1.5 rounded-full transition-all ${index === step ? 'w-8 bg-w-accent' : index < step ? 'w-1.5 bg-w-accent' : 'w-1.5 bg-w-surface2'}`} />)}
        </div>

        <div className="min-h-[360px] px-8 py-10 text-center">
          <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl border border-w-line bg-w-surface2/70">
            <Icon size={30} className="text-w-accent" />
          </div>
          <h2 className="text-xl font-semibold text-w-text">{current.title}</h2>
          <p className="mx-auto mt-4 max-w-md text-sm leading-6 text-w-dim">{current.description}</p>

          {step === 1 && (
            <div className="mx-auto mt-6 grid max-w-md gap-2 text-left sm:grid-cols-2">
              {(['member', 'reviewer', 'operator', 'admin'] as const).map((level) => (
                <div key={level} className="rounded-lg border border-w-line bg-w-surface2/40 p-3">
                  <p className="text-sm font-medium text-w-text">{ACCESS_LEVEL_COPY[level].label}</p>
                  <p className="mt-1 text-xs text-w-dim">{ACCESS_LEVEL_COPY[level].short}</p>
                </div>
              ))}
            </div>
          )}

          {step === 2 && (
            <div className="mx-auto mt-6 max-w-md space-y-2 text-left">
              {ACCESS_LEVELS.map((level) => (
                <div key={level} className="flex items-center gap-3 rounded-lg border border-w-line bg-w-surface2/40 px-3 py-2.5">
                  <Check size={15} className="text-w-accent" />
                  <span className="text-sm text-w-text">{ACCESS_LEVEL_COPY[level].label}</span>
                  <span className="ml-auto text-xs text-w-dim">{ACCESS_LEVEL_COPY[level].short}</span>
                </div>
              ))}
            </div>
          )}

          {step === 3 && (
            <div className="mx-auto mt-6 grid max-w-md gap-3 text-left sm:grid-cols-2">
              <div className="rounded-xl border border-w-line bg-w-surface2/40 p-3"><p className="text-sm font-medium text-w-text">Member</p><p className="mt-1 text-xs leading-5 text-w-dim">Drafts a proposal and waits.</p></div>
              <div className="rounded-xl border border-w-accent/40 bg-w-accent/10 p-3"><p className="text-sm font-medium text-w-text">Operator</p><p className="mt-1 text-xs leading-5 text-w-dim">Reviews, approves, and executes.</p></div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-w-line px-6 py-4">
          {step > 0 ? <button type="button" onClick={() => setStep((value) => value - 1)} className="inline-flex items-center gap-1 text-sm text-w-dim hover:text-w-text"><ChevronLeft size={16} />Back</button> : <button type="button" onClick={() => finish(false)} className="text-sm text-w-dim hover:text-w-text">Skip</button>}
          {isLast ? <button type="button" onClick={() => finish(true)} className="inline-flex items-center gap-1 rounded-lg bg-w-accent px-4 py-2.5 text-sm font-medium text-white hover:bg-w-accent-hi">Review access <ArrowRight size={16} /></button> : <button type="button" onClick={() => setStep((value) => value + 1)} className="inline-flex items-center gap-1 rounded-lg bg-w-accent px-4 py-2.5 text-sm font-medium text-white hover:bg-w-accent-hi">Next <ChevronRight size={16} /></button>}
        </div>
      </div>
    </div>
  )
}
