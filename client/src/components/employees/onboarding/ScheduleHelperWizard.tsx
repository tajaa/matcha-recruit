import { useState, type ReactNode } from 'react'
import {
  BarChart2,
  CalendarCheck2,
  Check,
  ChevronLeft,
  ChevronRight,
  FileWarning,
  Inbox,
  LayoutTemplate,
  Scale,
  X,
} from 'lucide-react'
import { Modal } from '../../ui'

type ScheduleHelperWizardProps = {
  open: boolean
  onClose(): void
}

type HelperStep = {
  eyebrow: string
  title: string
  body: string
  icon: typeof CalendarCheck2
  detail: ReactNode
}

const STEPS: HelperStep[] = [
  {
    eyebrow: '01 / Build a draft',
    title: 'Start with the weekly schedule',
    body: 'Use the week controls to move through dates, then add shifts from each day. Assign employees as you build the draft and use notes for details your team needs to see.',
    icon: CalendarCheck2,
    detail: <span>Draft changes stay private until you publish the week.</span>,
  },
  {
    eyebrow: '02 / Repeat the work',
    title: 'Use Templates for recurring coverage',
    body: 'Create reusable shift blocks in Templates, then generate a date range from them. This is the fastest way to build regular coverage without recreating every shift by hand.',
    icon: LayoutTemplate,
    detail: <span>Generated shifts are drafts, so review assignments and warnings before publishing.</span>,
  },
  {
    eyebrow: '03 / Handle changes',
    title: 'Review employee requests in one place',
    body: 'The Requests tab collects swap and time-off requests. Review the context, approve or decline the request, and reload the week to see the resulting schedule.',
    icon: Inbox,
    detail: <span>Approving a request changes the schedule; it does not publish a new week automatically.</span>,
  },
  {
    eyebrow: '04 / Check the plan',
    title: 'Use Intelligence before you publish',
    body: 'Intelligence turns the schedule into practical checks, including coverage, rest, overtime, and other patterns that are easy to miss in a weekly grid.',
    icon: BarChart2,
    detail: <span>It is an advisory review. Read each finding in context before changing the draft.</span>,
  },
  {
    eyebrow: '05 / Understand warnings',
    title: 'Resolve training and credential warnings',
    body: 'Amber warning markers identify employees with overdue training or lapsed credentials. Hover or focus the marker for the exact issue before assigning that person.',
    icon: FileWarning,
    detail: <span>Warnings are also sent to Ops so your team can follow up. They do not silently block scheduling.</span>,
  },
  {
    eyebrow: '06 / Publish with context',
    title: 'Check the law, then publish',
    body: 'Use Scheduling law to inspect researched thresholds and citations for a location. When the draft, requests, and warnings look right, publish the week from the Schedule tab.',
    icon: Scale,
    detail: <span>Published shifts are visible to employees. Treat the publish action as the final review checkpoint.</span>,
  },
]

export default function ScheduleHelperWizard({ open, onClose }: ScheduleHelperWizardProps) {
  const [step, setStep] = useState(0)
  const current = STEPS[step]
  const Icon = current.icon
  const last = step === STEPS.length - 1

  function close() {
    setStep(0)
    onClose()
  }

  return (
    <Modal open={open} onClose={close} bare>
      <div className="w-full max-w-lg rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-2xl sm:p-7">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-emerald-400">
            <span>Scheduling guide</span>
            <span className="text-zinc-700">/</span>
            <span>{current.eyebrow}</span>
          </div>
          <button onClick={close} className="text-zinc-600 hover:text-zinc-200" aria-label="Close scheduling guide"><X className="h-4 w-4" /></button>
        </div>
        <div className="mt-8 flex h-12 w-12 items-center justify-center rounded-xl border border-emerald-500/20 bg-emerald-500/10 text-emerald-300"><Icon className="h-6 w-6" /></div>
        <h2 className="mt-5 text-2xl font-light tracking-tight text-zinc-100">{current.title}</h2>
        <p className="mt-3 text-sm leading-6 text-zinc-400">{current.body}</p>
        <div className="mt-5 rounded-xl border border-zinc-800 bg-zinc-950 px-3.5 py-3 text-xs leading-5 text-zinc-500">{current.detail}</div>
        <div className="mt-7 flex items-center justify-between">
          <div className="flex items-center gap-1.5" aria-label={`Guide step ${step + 1} of ${STEPS.length}`}>
            {STEPS.map((item, index) => <span key={item.eyebrow} className={`h-1.5 rounded-full transition-all ${index === step ? 'w-7 bg-emerald-400' : index < step ? 'w-1.5 bg-emerald-700' : 'w-1.5 bg-zinc-700'}`} />)}
          </div>
          <div className="flex items-center gap-2">
            {!last && <button onClick={close} className="px-2 py-2 text-xs text-zinc-600 hover:text-zinc-300">Skip</button>}
            {step > 0 && <button onClick={() => setStep((value) => value - 1)} className="inline-flex items-center gap-1 rounded-lg border border-zinc-800 px-3 py-2 text-xs text-zinc-400 hover:text-zinc-100"><ChevronLeft className="h-3.5 w-3.5" /> Back</button>}
            <button onClick={() => last ? close() : setStep((value) => value + 1)} className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-medium text-white hover:bg-emerald-500">{last ? <Check className="h-3.5 w-3.5" /> : null}{last ? 'Start scheduling' : 'Next'}{!last && <ChevronRight className="h-3.5 w-3.5" />}</button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
