import { useState } from 'react'
import { ArrowLeft, ArrowRight, X, type LucideIcon } from 'lucide-react'

export type HowItWorksStep = {
  icon: LucideIcon
  title: string
  body: string
  detail?: string
}

/**
 * Generic "How it works" onboarding modal — a step-by-step walkthrough shown
 * for a Pilot-style feature. Feature pages own their own `title` + `steps`
 * content and just render this shell (see AnalysisPilot/HandbookPilot/
 * LegalDefense `index.tsx` for usage + the auto-show-once-on-first-visit
 * localStorage pattern each of them wires around it).
 *
 * Visual language mirrors BrokerPilot/HowItWorksModal.tsx (the original,
 * feature-specific version this generalizes) so all Pilot features feel the
 * same — that one is left as-is, not migrated onto this shell.
 */
export function HowItWorksModal({ title, steps, onClose }: {
  title: string
  steps: HowItWorksStep[]
  onClose: () => void
}) {
  const [step, setStep] = useState(0)
  const s = steps[step]
  const Icon = s.icon

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="w-full max-w-lg overflow-hidden rounded-xl border border-white/[0.08] bg-zinc-950"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-500">{title}</span>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-zinc-500 transition-colors hover:bg-white/[0.04] hover:text-zinc-200">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-6 py-6">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06]">
              <Icon className="h-4.5 w-4.5 text-emerald-400" />
            </span>
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-600">Step {step + 1} of {steps.length}</div>
              <h3 className="text-[15px] font-semibold text-zinc-100">{s.title}</h3>
            </div>
          </div>
          <p className="mt-4 text-sm leading-relaxed text-zinc-300">{s.body}</p>
          {s.detail && (
            <p className="mt-2.5 border-l-2 border-emerald-500/30 pl-3 text-[13px] leading-relaxed text-zinc-500">{s.detail}</p>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-white/[0.06] px-5 py-3">
          <div className="flex items-center gap-1.5">
            {steps.map((_, i) => (
              <button key={i} onClick={() => setStep(i)} aria-label={`Step ${i + 1}`}
                className={`h-1.5 rounded-full transition-all ${i === step ? 'w-5 bg-emerald-400' : 'w-1.5 bg-zinc-700 hover:bg-zinc-600'}`} />
            ))}
          </div>
          <div className="flex items-center gap-2">
            {step > 0 && (
              <button onClick={() => setStep(step - 1)}
                className="inline-flex items-center gap-1 rounded border border-white/[0.08] px-2.5 py-1 text-xs text-zinc-300 transition-colors hover:text-zinc-100">
                <ArrowLeft className="h-3 w-3" /> Back
              </button>
            )}
            {step < steps.length - 1 ? (
              <button onClick={() => setStep(step + 1)}
                className="inline-flex items-center gap-1 rounded bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white transition-colors hover:bg-emerald-500">
                Next <ArrowRight className="h-3 w-3" />
              </button>
            ) : (
              <button onClick={onClose}
                className="rounded bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white transition-colors hover:bg-emerald-500">
                Got it
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
