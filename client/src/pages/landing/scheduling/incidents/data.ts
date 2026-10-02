/** One illustrative case, told from report to signed copy. The stages, labels
 *  and rules are the product's own (HR cases); the people and times are the
 *  demo café's. */
export const CASE = {
  number: 'HRC-2026-0001',
  incident: 'IR-2026-10-3F78',
  title: 'Three missed shifts, no call',
  employee: 'Jonah B.',
  reporter: 'Ana R.',
} as const

/** The case checklist as HR sees it, with when each box ticked. */
export const CHECKLIST = [
  { label: 'Incident reviewed', at: 'Tue 8:02 AM' },
  { label: 'Write-up drafted', at: 'Tue 8:40 AM' },
  { label: 'HR legal review', at: 'Tue 8:41 AM' },
  { label: 'Approved to deliver', at: 'Tue 9:15 AM' },
  { label: 'Delivered to employee', at: 'Tue 9:30 AM' },
  { label: 'Signed copy uploaded', at: 'Wed 2:28 PM' },
  { label: 'Signed copy checked and filed', at: 'Wed 2:30 PM' },
] as const

/** What the handbook check reported. Only violated/bent at or above the
 *  threshold opens a case; "related" is shown, not flagged. */
export const FLAG_THRESHOLD = 60
export const MATCHES = [
  { policy: 'Attendance and Punctuality', relevance: 'Violated', confidence: 98, opens: true },
  { policy: 'Corrective Action', relevance: 'Related', confidence: 85, opens: false },
] as const

export type Outcome = 'holds' | 'noted' | 'fix'

export const OUTCOME: Record<Outcome, { label: string; means: string }> = {
  holds: { label: 'Holds for HR', means: 'Can’t be overridden. The draft waits for HR before anyone sends it.' },
  noted: { label: 'Noted for HR', means: 'HR sees it next to the letter when they decide.' },
  fix: { label: 'Manager fixes', means: 'Sent back to the manager with a plain note, before HR spends time on it.' },
}

export const LAYERS: { name: string; detail: string; example: string; outcome: Outcome }[] = [
  {
    name: 'Protected leave',
    detail: 'Absence dates that overlap leave the law protects.',
    example: 'Cal. Lab. Code § 246.5(c) · paid sick leave',
    outcome: 'holds',
  },
  {
    name: 'Discipline history',
    detail: 'Skips a step or repeats one, from this employee’s earlier cases.',
    example: 'Written warning · none on file in 12 months',
    outcome: 'noted',
  },
  {
    name: 'Letter structure',
    detail: 'Names the employee, dates the letter, states the expectation and the consequence, has a signature line.',
    example: 'Missing signature line',
    outcome: 'fix',
  },
  {
    name: 'Wording',
    detail: 'One read for tone, clarity, and anything that overreaches.',
    example: '“Always late” → the three dates',
    outcome: 'fix',
  },
]

/** What the signed-copy check reads off the page. */
export const SIGNED_CHECKS = [
  'Readable, not encrypted, all pages there',
  'Signed by the employee, and by the manager',
  'Printed name matches the case',
  'It’s the letter HR approved',
] as const
