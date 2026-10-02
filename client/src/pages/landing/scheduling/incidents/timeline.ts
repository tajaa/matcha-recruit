/** Canvas sizes and frame timeline for CaseComposition (the Incidents hero).
 *  Kept out of the component file so fast refresh keeps working. */
import type { Variant } from '../timeline'

export const CASE_SIZES: Record<Variant, { w: number; h: number; s: number }> = {
  wide: { w: 1600, h: 860, s: 1 },
  narrow: { w: 720, h: 1580, s: 1.6 },
}

export const CASE_DURATION = 660
/** Frame shown when motion is reduced: the closed case, full history. */
export const CASE_STILL = 600

export const K = {
  incident: 6,
  type: 22,
  typeEnd: 96,
  submit: 104,
  check: 116,
  scan: 122,
  scanEnd: 156,
  mark: 156,
  bar: 160,
  barEnd: 184,
  opened: 192,
  draft: 262,
  approve: 336,
  deliver: 388,
  signed: 446,
  closed: 516,
  fadeOut: 630,
}

export type Tone = 'red' | 'amber' | 'green'

/** The case's history, one entry per stage change. `col` is the HR Cases
 *  board column (New, HR review, Delivery, Signed copy, Done); `done` is how
 *  many of the seven checklist boxes are ticked after it. */
export const EVENTS: { at: number; when: string; text: string; col: number; stage: string; tone: Tone; done: number }[] = [
  { at: K.opened, when: 'Tue 8:02 AM', text: 'Case opened · Ana and HR notified', col: 0, stage: 'Flagged', tone: 'red', done: 1 },
  { at: K.draft, when: 'Tue 8:40 AM', text: 'Write-up in · reviewed, nothing held', col: 1, stage: 'HR review', tone: 'amber', done: 3 },
  { at: K.approve, when: 'Tue 9:15 AM', text: 'Approved · leave check re-run', col: 2, stage: 'Approved', tone: 'amber', done: 4 },
  { at: K.deliver, when: 'Tue 9:30 AM', text: 'Delivered to Jonah', col: 2, stage: 'Delivered', tone: 'amber', done: 5 },
  { at: K.signed, when: 'Wed 2:28 PM', text: 'Signed copy filed in Drive', col: 3, stage: 'Checking', tone: 'amber', done: 6 },
  { at: K.closed, when: 'Wed 2:30 PM', text: 'Signed copy checked · case closed', col: 4, stage: 'Closed', tone: 'green', done: 7 },
]

export const COLUMNS = ['New', 'HR review', 'Delivery', 'Signed copy', 'Done'] as const
