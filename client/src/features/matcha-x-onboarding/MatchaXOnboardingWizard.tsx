import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, X } from 'lucide-react'
import { matchaXOnboarding, type MatchaXStep } from '../../api/matchaXOnboarding'
import Step1Locations from './Step1Locations'
import Step2Policies from './Step2Policies'
import Step3People from './Step3People'
import Step4Build from './Step4Build'
import Step5Done from './Step5Done'

// Skip / completion is tracked client-side (no DB column) — mirrors the
// discipline-guide pattern. Bumping the version re-surfaces a reworked wizard.
export const MATCHA_X_ONBOARDING_KEY = 'matcha_x_onboarding_v1_dismissed'

const ORDER: MatchaXStep[] = ['locations', 'policies', 'people', 'build', 'done']

export default function MatchaXOnboardingWizard() {
  const navigate = useNavigate()
  const [step, setStep] = useState<MatchaXStep>('locations')
  const [loading, setLoading] = useState(true)
  const [handbookUrl, setHandbookUrl] = useState<string | null>(null)
  const [handbookName, setHandbookName] = useState<string | null>(null)

  useEffect(() => {
    matchaXOnboarding
      .status()
      .then((s) => {
        // Resume where they left off. A fully-onboarded tenant re-running lands
        // on Build (re-run the show) rather than being bounced straight to Done.
        setStep(s.step === 'done' ? 'build' : s.step)
      })
      .catch(() => {
        /* default to the first step */
      })
      .finally(() => setLoading(false))
  }, [])

  function advance() {
    setStep((cur) => ORDER[Math.min(ORDER.indexOf(cur) + 1, ORDER.length - 1)])
  }

  function dismiss() {
    try {
      localStorage.setItem(MATCHA_X_ONBOARDING_KEY, '1')
    } catch {
      /* ignore */
    }
  }

  function skip() {
    dismiss()
    navigate('/app')
  }

  async function finish() {
    dismiss()
    try {
      await matchaXOnboarding.complete()
    } catch {
      /* best-effort */
    }
    navigate('/app')
  }

  const wide = step === 'build' || step === 'done'

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-zinc-500 animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0c0c0e] px-4 py-10">
      <div className={(wide ? 'max-w-5xl' : 'max-w-xl') + ' mx-auto'}>
        <div className="flex items-center justify-between mb-8">
          <Stepper current={step} />
          {step !== 'done' && (
            <button
              onClick={skip}
              className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 shrink-0 ml-4"
            >
              Skip <span className="hidden sm:inline">/ do this later</span>
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {step === 'locations' && <Step1Locations onDone={advance} />}
        {step === 'policies' && (
          <Step2Policies
            onDone={advance}
            uploadedName={handbookName}
            onUploaded={(url, name) => {
              setHandbookUrl(url)
              setHandbookName(name)
            }}
          />
        )}
        {step === 'people' && <Step3People onDone={advance} />}
        {step === 'build' && <Step4Build handbookUrl={handbookUrl} onDone={advance} />}
        {step === 'done' && <Step5Done onFinish={finish} />}
      </div>
    </div>
  )
}

function Stepper({ current }: { current: MatchaXStep }) {
  const steps: { key: MatchaXStep; label: string }[] = [
    { key: 'locations', label: 'Locations' },
    { key: 'policies', label: 'Policies' },
    { key: 'people', label: 'People' },
    { key: 'build', label: 'Build' },
  ]
  const activeIdx = steps.findIndex((s) => s.key === current)
  // 'done' sits past Build — render every prior step as complete.
  const effIdx = current === 'done' ? steps.length : activeIdx
  return (
    <ol className="flex items-center gap-2 text-xs text-zinc-500">
      {steps.map((s, i) => {
        const done = i < effIdx
        const active = i === effIdx
        return (
          <li key={s.key} className="flex items-center gap-2">
            <span
              className={
                'w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-medium ' +
                (done
                  ? 'bg-emerald-700 text-white'
                  : active
                    ? 'bg-zinc-800 text-zinc-100 ring-1 ring-emerald-700'
                    : 'bg-zinc-900 text-zinc-600')
              }
            >
              {i + 1}
            </span>
            <span className={active ? 'text-zinc-200' : ''}>{s.label}</span>
            {i < steps.length - 1 && <span className="text-zinc-700">→</span>}
          </li>
        )
      })}
    </ol>
  )
}
