/**
 * Master-admin onboarding wizard shell.
 *
 * Resolves the session from the URL param, renders a left-rail step
 * indicator, and dispatches to one of the six step components. Each
 * step owns its own save + advance — the shell just tracks which step
 * is active and refetches on update.
 */
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Check, Loader2 } from 'lucide-react'

import { adminOnboarding } from '../../api/adminOnboarding'
import type { OnboardingSessionDetail, OnboardingStep } from '../../api/adminOnboarding'
import {
  Step1Basics,
  Step2Size,
  Step3Locations,
  Step4Scope,
  Step5Gaps,
  Step6Review,
} from '../../features/admin-onboarding/Steps'

const STEP_ORDER: OnboardingStep[] = [
  'basics',
  'size',
  'locations',
  'scope',
  'gaps',
  'review',
  'done',
]

const STEP_LABELS: Record<OnboardingStep, string> = {
  basics: 'Basics',
  size: 'Headcount',
  locations: 'Locations',
  scope: 'AI Scope',
  gaps: 'Coverage',
  review: 'Review',
  done: 'Done',
}

export default function AdminOnboardingWizard() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [session, setSession] = useState<OnboardingSessionDetail | null>(null)
  const [activeStep, setActiveStep] = useState<OnboardingStep>('basics')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!sessionId) return
    setLoading(true)
    setError(null)
    try {
      const s = await adminOnboarding.getSession(sessionId)
      setSession(s)
      setActiveStep(s.step === 'done' ? 'review' : s.step)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load session')
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  function onUpdated(s: OnboardingSessionDetail) {
    setSession(s)
  }

  function advanceTo(next: OnboardingStep) {
    setActiveStep(next)
  }

  function next() {
    const idx = STEP_ORDER.indexOf(activeStep)
    if (idx >= 0 && idx < STEP_ORDER.length - 1) {
      advanceTo(STEP_ORDER[idx + 1])
    }
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center gap-2 text-sm text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading session…
      </div>
    )
  }

  if (error || !session) {
    return (
      <div className="p-6">
        <div className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-300">
          {error || 'Session not found.'}
        </div>
        <Link to="/admin/onboarding" className="inline-block mt-3 text-sm text-emerald-300 hover:underline">
          ← Back to onboarding
        </Link>
      </div>
    )
  }

  return (
    <div className="p-6 flex gap-8">
      <aside className="w-56 shrink-0">
        <Link
          to="/admin/onboarding"
          className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 mb-4"
        >
          <ArrowLeft className="w-3 h-3" /> All sessions
        </Link>
        <h2 className="text-sm font-medium text-zinc-100 mb-3">
          {session.basics?.business_name || 'New onboarding'}
        </h2>
        <ol className="space-y-1.5">
          {STEP_ORDER.filter((s) => s !== 'done').map((step, idx) => {
            const stepIdx = idx
            const persistedIdx = STEP_ORDER.indexOf(session.step)
            const completed = persistedIdx > stepIdx || session.status === 'finalized'
            const active = step === activeStep
            const reachable = stepIdx <= persistedIdx
            return (
              <li key={step}>
                <button
                  onClick={() => reachable && advanceTo(step)}
                  disabled={!reachable}
                  className={`w-full text-left flex items-center gap-2 px-2 py-1.5 rounded-md text-sm ${
                    active
                      ? 'bg-emerald-500/15 text-emerald-200'
                      : completed
                        ? 'text-zinc-300 hover:bg-zinc-900/50'
                        : 'text-zinc-500'
                  } ${!reachable ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}`}
                >
                  <span
                    className={`flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-semibold ${
                      completed
                        ? 'bg-emerald-500/30 text-emerald-200'
                        : active
                          ? 'bg-emerald-500 text-zinc-950'
                          : 'bg-zinc-800 text-zinc-500'
                    }`}
                  >
                    {completed ? <Check className="w-3 h-3" /> : idx + 1}
                  </span>
                  {STEP_LABELS[step]}
                </button>
              </li>
            )
          })}
        </ol>
        {session.status === 'finalized' && (
          <div className="mt-4 text-[11px] uppercase tracking-wider text-emerald-300">
            Finalized
          </div>
        )}
      </aside>

      <section className="flex-1 min-w-0">
        {activeStep === 'basics' && (
          <Step1Basics session={session} onUpdated={onUpdated} onNext={next} />
        )}
        {activeStep === 'size' && (
          <Step2Size session={session} onUpdated={onUpdated} onNext={next} />
        )}
        {activeStep === 'locations' && (
          <Step3Locations session={session} onUpdated={onUpdated} onNext={next} />
        )}
        {activeStep === 'scope' && (
          <Step4Scope session={session} onUpdated={onUpdated} onNext={next} />
        )}
        {activeStep === 'gaps' && (
          <Step5Gaps session={session} onUpdated={onUpdated} onNext={next} />
        )}
        {activeStep === 'review' && (
          <Step6Review session={session} onUpdated={onUpdated} onNext={next} />
        )}
      </section>
    </div>
  )
}
