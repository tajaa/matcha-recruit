import { useState } from 'react'
import { Modal, Button } from '../../components/ui'
import { Gavel, Sparkles, PenLine, TrendingUp } from 'lucide-react'

// Bumping the version resets the "seen" flag for everyone, so a reworked
// guide re-surfaces once. Keep the old key around only if you need it.
export const DISCIPLINE_GUIDE_KEY = 'matcha_discipline_guide_v1_dismissed'

type Step = {
  icon: typeof Gavel
  title: string
  body: string
  points: string[]
}

const STEPS: Step[] = [
  {
    icon: Gavel,
    title: 'Progressive performance action',
    body:
      'Performance Action tracks corrective steps in order — verbal → written → PIP → final → suspension — so escalation is consistent and defensible across employees.',
    points: [
      'One record per incident; history drives the next recommended level.',
      'Records expire after a configurable lookback window so old issues fall off.',
    ],
  },
  {
    icon: Sparkles,
    title: 'Issue a record with an AI recommendation',
    body:
      'Click “New record”, pick the employee, infraction type, and severity, then “Preview recommendation”. The engine reads prior records over the lookback window and suggests the right level.',
    points: [
      'Auto-to-written and termination-review flags surface automatically.',
      'You can override the recommended level — an override reason (20+ chars) is required.',
    ],
  },
  {
    icon: PenLine,
    title: 'Meetings & signatures',
    body:
      'After issuing, a record moves through Pending Meeting → Pending Signature → Active. Capture the employee acknowledgement via the e-signature workflow on the record detail page.',
    points: [
      'Status badges on the list show exactly what each record is waiting on.',
      'Signed records become Active and start their expiry clock.',
    ],
  },
  {
    icon: TrendingUp,
    title: 'Escalation, expiry & settings',
    body:
      'Stale records auto-close, and repeat infractions escalate to the next level on the next issue. Tune levels, lookback windows, and infraction policies under Settings.',
    points: [
      'Escalated records are flagged in red on the list for quick triage.',
      'Adjust the policy matrix any time in Performance Action → Settings.',
    ],
  },
]

type Props = {
  open: boolean
  onClose: () => void
}

export default function DisciplineGuideModal({ open, onClose }: Props) {
  const [idx, setIdx] = useState(0)
  const step = STEPS[idx]
  const Icon = step.icon
  const isLast = idx === STEPS.length - 1

  function close() {
    setIdx(0)
    onClose()
  }

  return (
    <Modal open={open} onClose={close} title="How Performance Action works" width="lg">
      <div className="space-y-5">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 w-9 h-9 rounded-lg bg-emerald-900/40 ring-1 ring-emerald-800 flex items-center justify-center shrink-0">
            <Icon className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-zinc-100">{step.title}</h3>
            <p className="text-sm text-zinc-400 mt-1">{step.body}</p>
          </div>
        </div>

        <ul className="text-sm text-zinc-400 space-y-1 list-disc list-inside pl-1">
          {step.points.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>

        <div className="flex items-center gap-1.5 pt-1">
          {STEPS.map((_, i) => (
            <span
              key={i}
              className={
                'h-1.5 rounded-full transition-all ' +
                (i === idx ? 'w-6 bg-emerald-500' : 'w-1.5 bg-zinc-700')
              }
            />
          ))}
        </div>

        <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
          <Button variant="ghost" onClick={close}>Skip</Button>
          <div className="flex gap-2">
            {idx > 0 && (
              <Button variant="ghost" onClick={() => setIdx((i) => i - 1)}>Back</Button>
            )}
            {isLast ? (
              <Button onClick={close}>Got it</Button>
            ) : (
              <Button onClick={() => setIdx((i) => i + 1)}>Next</Button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  )
}
