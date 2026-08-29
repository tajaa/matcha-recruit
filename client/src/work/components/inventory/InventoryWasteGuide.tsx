import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ArrowRight, Bot, Check, ClipboardList, MessageSquare, PackageCheck, SlidersHorizontal, X, type LucideIcon } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Button, Modal, WizardStepper } from '../../../components/ui'
import type { WizardStep } from '../../../components/ui/WizardStepper'
import { useWorkBase } from '../../routes/WorkSurfaceContext'

type Step = { key: string; label: string; title: string; description: string; location: string; bullets: string[]; icon: LucideIcon; destination: (base: string) => string }

const STEPS: Step[] = [
  { key: 'huume', label: '@huume', title: 'Report loss from team chat', description: 'In any team channel, mention @huume with what was discarded and why. Huume stages the waste record for you to confirm.', location: 'Team chat → any channel → @huume', bullets: ['Example: “@huume tossed 3 boxes of gloves; package was torn.”', 'Confirm the staged card before it changes inventory.', 'Use the Waste page for manager-entered records and trend review.'], icon: MessageSquare, destination: (base) => `${base}/inventory/waste#huume-capture` },
  { key: 'capture', label: 'Capture', title: 'Record loss as it happens', description: 'Use Record waste for a confirmed discarded item and choose the closest reason.', location: 'Inventory → Waste → Record waste', bullets: ['Use theft only for an explicit manager decision; chat reports are intentionally classified as unknown.', 'Every entry creates a ledger record and reduces on-hand stock.', 'Reason codes make the weekly pattern actionable.'], icon: ClipboardList, destination: (base) => `${base}/inventory/waste#waste-record` },
  { key: 'review', label: 'Review', title: 'Review the pattern before reacting', description: 'Start with value, reason, category, and top bleeders—not a single incident.', location: 'Inventory → Waste → dashboard sections and Ask the waste analyst', bullets: ['Waste / revenue appears when committed sales are available.', 'Theoretical vs actual use flags a possible portion or mapping issue.', 'Ask the analyst for a read-only, cited summary of what changed.'], icon: Bot, destination: (base) => `${base}/inventory/waste#waste-review` },
  { key: 'protect', label: 'Protect', title: 'Make perishability visible', description: 'On each item, add category, shelf life, and usable yield, then receive dated lots.', location: 'Inventory → select an item → Perishable settings and Lots expiring within a year', bullets: ['Shelf life caps a recommendation to stock that can be used in time.', 'Dated lots deplete earliest-expiring first as stock is used or discarded.', 'Yield improves recipe-based theoretical usage.'], icon: PackageCheck, destination: (base) => `${base}/inventory#waste-protect` },
  { key: 'par', label: 'PAR', title: 'Use predictive PARs with guardrails', description: 'Review an item recommendation, apply it deliberately, or enroll a stable item in automatic updates.', location: 'Inventory → select an item → Predictive par; portfolio controls: Inventory → Forecast', bullets: ['Forecasting needs committed sales and mappings before it can recommend a PAR.', 'Maximum drift blocks a surprising automatic change.', 'PAR history explains every applied update.'], icon: SlidersHorizontal, destination: (base) => `${base}/inventory/forecast#waste-par` },
]

const WASTE_GUIDE_STORAGE_KEY = 'matcha-inventory-waste-guide-v1'

function storageHasSeen(getStorage: () => Storage, key: string) {
  try {
    return getStorage().getItem(key) === '1'
  } catch {
    return false
  }
}

function guideWasSeen(autoOpenKey: string) {
  const key = `${WASTE_GUIDE_STORAGE_KEY}:${autoOpenKey}`
  return storageHasSeen(() => localStorage, key) || storageHasSeen(() => sessionStorage, key)
}

function markGuideSeen(autoOpenKey: string) {
  const key = `${WASTE_GUIDE_STORAGE_KEY}:${autoOpenKey}`
  try { localStorage.setItem(key, '1') } catch { /* storage may be blocked */ }
  try { sessionStorage.setItem(key, '1') } catch { /* storage may be blocked */ }
}

export default function InventoryWasteGuide({ open, onClose, initialStep = 0, autoOpenKey }: { open: boolean; onClose: () => void; initialStep?: number; autoOpenKey?: string }) {
  const base = useWorkBase()
  const navigate = useNavigate()
  const location = useLocation()
  const requestedStepValue = new URLSearchParams(location.search).get('inventoryGuideStep')
  const requestedStep = requestedStepValue === null ? Number.NaN : Number(requestedStepValue)
  const hasRouteStep = Number.isInteger(requestedStep) && requestedStep >= 0 && requestedStep < STEPS.length
  const routeStep = hasRouteStep ? requestedStep : initialStep
  const [step, setStep] = useState(routeStep)
  const [autoDismissed, setAutoDismissed] = useState(false)
  const steps = useMemo<WizardStep[]>(() => STEPS.map(({ key, label }) => ({ key, label })), [])
  const shouldAutoOpen = autoOpenKey !== undefined && !autoDismissed && !guideWasSeen(autoOpenKey)
  const current = STEPS[step]
  const Icon = current.icon

  useEffect(() => { setStep(routeStep) }, [routeStep, open])
  useEffect(() => {
    if (!location.hash) return
    const anchor = document.getElementById(location.hash.slice(1))
    if (anchor) requestAnimationFrame(() => anchor.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }, [location.hash])
  function close() {
    if (autoOpenKey !== undefined) markGuideSeen(autoOpenKey)
    setAutoDismissed(true)
    if (hasRouteStep) {
      const search = new URLSearchParams(location.search)
      search.delete('inventoryGuideStep')
      navigate({
        pathname: location.pathname,
        search: search.size ? `?${search.toString()}` : '',
        hash: location.hash,
      }, { replace: true })
    }
    onClose()
  }
  const isAtCurrentSection = `${location.pathname}${location.hash}` === STEPS[step].destination(base)
  function moveTo(nextStep: number) {
    const destination = STEPS[nextStep].destination(base)
    navigate(`${destination.split('#')[0]}?inventoryGuideStep=${nextStep}${destination.includes('#') ? `#${destination.split('#')[1]}` : ''}`)
  }

  return <Modal open={open || shouldAutoOpen || hasRouteStep} onClose={close} bare>
    <div className="max-h-[calc(100dvh-2rem)] w-full max-w-2xl overflow-y-auto rounded-2xl border border-w-line bg-w-surface shadow-2xl">
      <div className="flex items-center justify-between border-b border-w-line px-5 py-4"><div className="flex items-center gap-2 text-sm font-medium text-w-text"><PackageCheck className="h-4 w-4 text-w-accent" />Waste & predictive PAR guide</div><button type="button" onClick={close} className="rounded-md p-1.5 text-w-dim hover:bg-w-surface2 hover:text-w-text" aria-label="Close waste guide"><X className="h-4 w-4" /></button></div>
      <div className="overflow-x-auto border-b border-w-line px-5 py-4"><WizardStepper steps={steps} activeIndex={step} /></div>
      <div className="grid gap-5 px-5 py-6 sm:grid-cols-[auto_1fr]"><div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-w-accent/20 bg-w-accent/10 text-w-accent"><Icon className="h-8 w-8" /></div><div><p className="text-[10px] font-medium uppercase tracking-[0.16em] text-w-accent">Step {step + 1} of {STEPS.length}</p><h2 className="mt-1 text-xl font-semibold text-w-text">{current.title}</h2><p className="mt-2 text-sm leading-6 text-w-dim">{current.description}</p><div className="mt-4 rounded-lg border border-w-accent/20 bg-w-accent/10 px-3 py-2 text-xs text-w-text"><span className="font-medium text-w-accent">Where to find it: </span>{current.location}</div><ul className="mt-4 space-y-2 text-sm text-w-text">{current.bullets.map((bullet) => <li key={bullet} className="flex gap-2.5"><Check className="mt-0.5 h-4 w-4 shrink-0 text-w-accent" /><span>{bullet}</span></li>)}</ul></div></div>
      <div className="flex items-center justify-between border-t border-w-line px-5 py-4"><button type="button" onClick={close} className="text-sm text-w-dim hover:text-w-text">Skip guide</button><div className="flex gap-2"><Button variant="ghost" size="sm" disabled={step === 0} onClick={() => moveTo(step - 1)}><ArrowLeft className="h-3.5 w-3.5" />Back</Button>{step < STEPS.length - 1 ? <Button size="sm" onClick={() => moveTo(isAtCurrentSection ? step + 1 : step)}>Next<ArrowRight className="h-3.5 w-3.5" /></Button> : <Button size="sm" onClick={close}>Finish guide</Button>}</div></div>
    </div>
  </Modal>
}
