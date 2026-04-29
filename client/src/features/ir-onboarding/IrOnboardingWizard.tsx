import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { api } from '../../api/client'
import Step1CompanyInfo from './Step1CompanyInfo'
import Step2Employees from './Step2Employees'
import Step3AnonymousReporting from './Step3AnonymousReporting'
import Step4Done from './Step4Done'

type WizardStep = 'company_info' | 'employees' | 'anonymous' | 'ready'

const ORDER: WizardStep[] = ['company_info', 'employees', 'anonymous', 'ready']

interface OnboardingStatus {
  step: WizardStep
  locations_count: number
  employees_count: number
  anonymous_token_present: boolean
  completed_at: string | null
}

export default function IrOnboardingWizard() {
  const navigate = useNavigate()
  const [serverStep, setServerStep] = useState<WizardStep | null>(null)
  const [localStep, setLocalStep] = useState<WizardStep | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    try {
      const data = await api.get<OnboardingStatus>('/ir-onboarding/status')
      setServerStep(data.step)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load onboarding status')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  // The displayed step is whichever is further along: the server's
  // implied state (driven by data presence) OR a local manual advance
  // (Skip / Continue clicks). Without the local override the user
  // would loop on a step they explicitly advanced past with no data.
  const step: WizardStep = (() => {
    const s = serverStep ?? 'company_info'
    if (!localStep) return s
    return ORDER.indexOf(localStep) > ORDER.indexOf(s) ? localStep : s
  })()

  function advance() {
    const next = ORDER[Math.min(ORDER.indexOf(step) + 1, ORDER.length - 1)]
    setLocalStep(next)
    refresh()
  }

  async function complete() {
    try {
      await api.post('/ir-onboarding/complete')
      navigate('/app/ir')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to complete onboarding')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-zinc-500 animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4">
        <div className="max-w-sm w-full text-center">
          <h1 className="text-xl font-semibold text-zinc-100 mb-2">Onboarding error</h1>
          <p className="text-sm text-red-400">{error}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0c0c0e] flex items-center justify-center px-4 py-10">
      <div className="max-w-xl w-full">
        <Stepper current={step} />
        <div className="mt-8">
          {step === 'company_info' && <Step1CompanyInfo onDone={advance} />}
          {step === 'employees' && <Step2Employees onDone={advance} />}
          {step === 'anonymous' && <Step3AnonymousReporting onDone={advance} />}
          {step === 'ready' && <Step4Done onContinue={complete} />}
        </div>
      </div>
    </div>
  )
}

function Stepper({ current }: { current: WizardStep }) {
  const steps: { key: WizardStep; label: string }[] = [
    { key: 'company_info', label: 'Locations' },
    { key: 'employees', label: 'Employees' },
    { key: 'anonymous', label: 'Anonymous reports' },
    { key: 'ready', label: 'Done' },
  ]
  const activeIdx = steps.findIndex((s) => s.key === current)
  return (
    <ol className="flex items-center gap-2 text-xs text-zinc-500">
      {steps.map((s, i) => {
        const done = i < activeIdx
        const active = i === activeIdx
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
