import { BriefcaseBusiness, Check, ChevronLeft, ChevronRight, ClipboardCheck, LayoutTemplate, MousePointer2, Send, Sparkles, Users, X } from 'lucide-react'
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
    eyebrow: '01 / See before you decide',
    title: 'Start from the inputs rail',
    body: 'The left rail is what a good scheduler keeps in their head: each person’s hours this week as a bar against the 40h policy tick, who is confirmed available, who is away, the open seats by day, and whether this state’s scheduling law is on file. Huume reads exactly this list before it names anyone.',
    icon: Users,
    detail: <span>Click a person to fade every full shift they are not on; drag them onto a shift to assign. The policy lines are house rules, not law — the law status is the banner above them.</span>,
  },
  {
    eyebrow: '02 / Define the work',
    title: 'Jobs, credentials and week setup live in the rail',
    body: 'Open Jobs to add the work areas your location schedules and who is qualified for each; open Week setup for hours, week start, staffing pattern and the leader rule. Huume refuses to build a week until setup is saved — the rail says what is missing.',
    icon: BriefcaseBusiness,
    detail: <span>Required credentials belong to the job. An extracted or unconfirmed expiration date is never trusted for scheduling.</span>,
  },
  {
    eyebrow: '03 / Build on the board',
    title: 'The board still works the way you know',
    body: 'Click any time slot to create a draft shift, drag a person from the rail onto a shift or an empty slot, drag an assignment to move it, click a shift to edit its time, role, staffing, break and notes. Draft changes save automatically.',
    icon: MousePointer2,
    detail: <span>Nothing is visible to employees until you publish. Published shifts are locked unless you turn on Edit published.</span>,
  },
  {
    eyebrow: '04 / Ask Huume',
    title: 'Huume is always on the right',
    body: 'Ask in plain language or by voice: fill the open shifts, build the whole week, move someone, cover a call-out. The server picks people under the staffing rules; Huume relays what it staged, what it refused and why, and what stayed open.',
    icon: Sparkles,
    detail: <span>Every AI-drafted change is staged first. The card in the thread is where you confirm or cancel it.</span>,
  },
  {
    eyebrow: '05 / Review before it is real',
    title: 'The review pane shows what a change will do',
    body: 'When Huume stages something, Review opens: each person’s hours before → after on the same bar as the rail, what is staged, what was refused (and why), the seats still open, statutory advisories with their statute, and coverage findings. Click a row to see it on the board or to ask Huume about it.',
    icon: ClipboardCheck,
    detail: <span>The compliance banner is the server’s sentence, not ours. “NOT verified” means exactly that — confirming is you accepting it.</span>,
  },
  {
    eyebrow: '06 / Run scenarios',
    title: 'Simulate a fill before you commit',
    body: 'New scenario in the strip runs a free server-side fill: all open shifts, one job, or the shifts you selected; only one person, or leaving people out; splits allowed or not. Each chip is a simulation you can review, compare with a second (shift-click), stage in the thread, or apply directly.',
    icon: LayoutTemplate,
    detail: <span>Nothing is written until you apply or confirm. Discarded scenarios are gone; the ones you leave behind are cleared when you change week.</span>,
  },
  {
    eyebrow: '07 / Publish',
    title: 'Publish when the week reads right',
    body: 'Publish in the top bar makes the drafts live. Break rules, waivers, credential expiry protection and the audit trail all keep working exactly as before.',
    icon: Send,
    detail: <span>Two weeks before a Food Handler Card expires the team is reminded; at expiry, affected future shifts are removed and new assignments are blocked until a renewed card is approved.</span>,
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
            <span>Schedule Pilot</span>
            <span className="text-zinc-700">·</span>
            <span>{current.eyebrow}</span>
          </div>
          <button onClick={close} className="text-zinc-600 hover:text-zinc-200" aria-label="Close Schedule Pilot guide"><X className="h-4 w-4" /></button>
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
