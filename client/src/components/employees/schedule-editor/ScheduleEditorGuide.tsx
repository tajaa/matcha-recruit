import { ArrowLeftRight, BriefcaseBusiness, Check, ChevronLeft, ChevronRight, ClipboardCheck, LayoutTemplate, MousePointer2, Send, ShieldAlert, Sparkles, Tag, Users, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Modal } from '../../ui'

interface ScheduleEditorGuideProps {
  open: boolean
  onClose(): void
}

type GuideStep = {
  eyebrow: string
  title: string
  body: string
  icon: typeof MousePointer2
  detail: ReactNode
}

const STEPS: GuideStep[] = [
  {
    eyebrow: '01 / Define the work',
    title: 'Create jobs before you build shifts',
    body: 'Open the Jobs tab and add the work areas your location schedules, such as Box Office, Concessions, or Ushers. Jobs are the labels that make qualification rules possible; role and department remain optional free-text context.',
    icon: BriefcaseBusiness,
    detail: <span>Start with a separate job for each area where the qualified roster is different.</span>,
  },
  {
    eyebrow: '02 / Define eligibility',
    title: 'Set qualifications and credential rules',
    body: 'Expand a job to choose qualified employees and add required credentials, such as a Food Handler Card. In the employee record’s Credentials tab, upload the document and confirm its expiration date when approving it.',
    icon: ClipboardCheck,
    detail: <span>Required credentials belong to the job, so they affect only relevant work. An extracted or unconfirmed expiration date is never trusted for scheduling.</span>,
  },
  {
    eyebrow: '03 / Attach the work',
    title: 'Choose a job on the shift',
    body: 'When you create or edit a shift, choose its Job. You can also choose a Job on a template block so every generated shift inherits the same qualification rule.',
    icon: Tag,
    detail: <span>Leaving Job empty keeps the shift ungated, so existing shifts and general-purpose work remain unchanged.</span>,
  },
  {
    eyebrow: '04 / Repeat the pattern',
    title: 'Generate a qualified week',
    body: 'Use Templates to define recurring blocks, attach each block to a job, and generate draft shifts across a date range. Review the generated week before publishing.',
    icon: LayoutTemplate,
    detail: <span>Generated shifts carry the block job automatically; you do not need to reselect it for every date.</span>,
  },
  {
    eyebrow: '05 / Build a draft',
    title: 'Start with the empty grid',
    body: 'Click any time slot to create a draft shift, or drag an employee from the roster onto an empty slot to create a shift with that person already assigned.',
    icon: MousePointer2,
    detail: <span>Draft changes save automatically. Nothing is visible to employees until you publish.</span>,
  },
  {
    eyebrow: '06 / Staff it',
    title: 'Place people where they belong',
    body: 'Drag a roster person onto a shift to assign them. Drag an assignment chip to another shift to move them, or click a person and then a shift if you prefer not to drag.',
    icon: Users,
    detail: <span>Roster qualifications can be overridden deliberately and are audit-logged. Conflicts, availability, staffing limits, and missing or expired required credentials cannot be overridden.</span>,
  },
  {
    eyebrow: '07 / Review and publish',
    title: 'Review the week before it goes live',
    body: 'Click any shift to edit its exact time, role, location, staffing, break, and notes. When the draft looks right, use Publish in the top bar.',
    icon: Send,
    detail: <span>Published shifts are locked by default. Turn on Edit published only when you intentionally need to change live schedules.</span>,
  },
  {
    eyebrow: '08 / Ask Huume',
    title: 'Build shifts by talking, not clicking',
    body: 'Use Ask Huume in the top bar to build the whole week from confirmed availability, describe a smaller change in plain language, or dictate by voice. Huume shows a proposal first; generated schedules land as editable drafts and only you publish them.',
    icon: Sparkles,
    detail: <span>Every AI-drafted change lands as an editable draft first — nothing is assigned or published without your confirmation.</span>,
  },
  {
    eyebrow: '09 / Compliance guidance',
    title: 'Review break rules and waivers before you publish',
    body: 'Assignments now carry individualized compliance guidance — break-rule requirements checked against the shift, and any waiver attestations on file for that employee. Unresolved warnings also surface as events in Ops so the team catches them outside the editor.',
    icon: ShieldAlert,
    detail: <span>A guidance note does not block the shift. Read it, resolve it, or record a waiver attestation before you publish.</span>,
  },
  {
    eyebrow: '10 / Keep cards current',
    title: 'Food-handler expiry protection runs automatically',
    body: 'Two weeks before a Food Handler Card expires, the employee and relevant managers receive a reminder. At expiry, future affected shifts are removed and every new assignment, move, Huume change, and publish is blocked until a renewed card is approved.',
    icon: ArrowLeftRight,
    detail: <span>This protection starts only when Food Handler Card is required for the job. Approving a replacement card clears the scheduling block; every enforcement decision is audit-logged.</span>,
  },
]

export default function ScheduleEditorGuide({ open, onClose }: ScheduleEditorGuideProps) {
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
            <span>Schedule editor</span>
            <span className="text-zinc-700">·</span>
            <span>{current.eyebrow}</span>
          </div>
          <button onClick={close} className="text-zinc-600 hover:text-zinc-200" aria-label="Close schedule editor guide"><X className="h-4 w-4" /></button>
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
