import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ArrowRight, Bot, Check, ClipboardList, PackageCheck, SlidersHorizontal, X, type LucideIcon } from 'lucide-react'
import { Button, Modal, WizardStepper } from '../../../components/ui'
import type { WizardStep } from '../../../components/ui/WizardStepper'

type Step = { key: string; label: string; title: string; description: string; bullets: string[]; icon: LucideIcon }

const STEPS: Step[] = [
  { key: 'capture', label: 'Capture', title: 'Record loss as it happens', description: 'Use Record waste for a confirmed discarded item and choose the closest reason.', bullets: ['Use theft only for an explicit manager decision; chat reports are intentionally classified as unknown.', 'Every entry creates a ledger record and reduces on-hand stock.', 'Reason codes make the weekly pattern actionable.'], icon: ClipboardList },
  { key: 'review', label: 'Review', title: 'Review the pattern before reacting', description: 'Start with value, reason, category, and top bleeders—not a single incident.', bullets: ['Waste / revenue appears when committed sales are available.', 'Theoretical vs actual use flags a possible portion or mapping issue.', 'Ask the analyst for a read-only, cited summary of what changed.'], icon: Bot },
  { key: 'protect', label: 'Protect', title: 'Make perishability visible', description: 'On each item, add category, shelf life, and usable yield, then receive dated lots.', bullets: ['Shelf life caps a recommendation to stock that can be used in time.', 'Dated lots deplete earliest-expiring first as stock is used or discarded.', 'Yield improves recipe-based theoretical usage.'], icon: PackageCheck },
  { key: 'par', label: 'PAR', title: 'Use predictive PARs with guardrails', description: 'Review an item recommendation, apply it deliberately, or enroll a stable item in automatic updates.', bullets: ['Forecasting needs committed sales and mappings before it can recommend a PAR.', 'Maximum drift blocks a surprising automatic change.', 'PAR history explains every applied update.'], icon: SlidersHorizontal },
]

export const INVENTORY_WASTE_GUIDE_STORAGE_KEY = 'matcha-inventory-waste-guide-v1'

export default function InventoryWasteGuide({ open, onClose, initialStep = 0, autoOpenKey }: { open: boolean; onClose: () => void; initialStep?: number; autoOpenKey?: string }) {
  const [step, setStep] = useState(initialStep)
  const [autoDismissed, setAutoDismissed] = useState(false)
  const steps = useMemo<WizardStep[]>(() => STEPS.map(({ key, label }) => ({ key, label })), [])
  const storageKey = autoOpenKey ? `${INVENTORY_WASTE_GUIDE_STORAGE_KEY}:${autoOpenKey}` : ''
  const shouldAutoOpen = Boolean(storageKey) && !autoDismissed && (() => { try { return localStorage.getItem(storageKey) !== '1' } catch { return false } })()
  const current = STEPS[step]
  const Icon = current.icon

  useEffect(() => { setStep(initialStep) }, [initialStep, open])
  useEffect(() => { if (shouldAutoOpen) { try { localStorage.setItem(storageKey, '1') } catch { /* storage may be blocked */ } } }, [shouldAutoOpen, storageKey])
  function close() { setAutoDismissed(true); onClose() }

  return <Modal open={open || shouldAutoOpen} onClose={close} bare>
    <div className="max-h-[calc(100dvh-2rem)] w-full max-w-2xl overflow-y-auto rounded-2xl border border-w-line bg-w-surface shadow-2xl">
      <div className="flex items-center justify-between border-b border-w-line px-5 py-4"><div className="flex items-center gap-2 text-sm font-medium text-w-text"><PackageCheck className="h-4 w-4 text-w-accent" />Waste & predictive PAR guide</div><button type="button" onClick={close} className="rounded-md p-1.5 text-w-dim hover:bg-w-surface2 hover:text-w-text" aria-label="Close waste guide"><X className="h-4 w-4" /></button></div>
      <div className="overflow-x-auto border-b border-w-line px-5 py-4"><WizardStepper steps={steps} activeIndex={step} /></div>
      <div className="grid gap-5 px-5 py-6 sm:grid-cols-[auto_1fr]"><div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-w-accent/20 bg-w-accent/10 text-w-accent"><Icon className="h-8 w-8" /></div><div><p className="text-[10px] font-medium uppercase tracking-[0.16em] text-w-accent">Step {step + 1} of {STEPS.length}</p><h2 className="mt-1 text-xl font-semibold text-w-text">{current.title}</h2><p className="mt-2 text-sm leading-6 text-w-dim">{current.description}</p><ul className="mt-4 space-y-2 text-sm text-w-text">{current.bullets.map((bullet) => <li key={bullet} className="flex gap-2.5"><Check className="mt-0.5 h-4 w-4 shrink-0 text-w-accent" /><span>{bullet}</span></li>)}</ul></div></div>
      <div className="flex items-center justify-between border-t border-w-line px-5 py-4"><button type="button" onClick={close} className="text-sm text-w-dim hover:text-w-text">Skip guide</button><div className="flex gap-2"><Button variant="ghost" size="sm" disabled={step === 0} onClick={() => setStep((value) => value - 1)}><ArrowLeft className="h-3.5 w-3.5" />Back</Button>{step < STEPS.length - 1 ? <Button size="sm" onClick={() => setStep((value) => value + 1)}>Next<ArrowRight className="h-3.5 w-3.5" /></Button> : <Button size="sm" onClick={close}>Finish guide</Button>}</div></div>
    </div>
  </Modal>
}
