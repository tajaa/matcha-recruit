/** Copy for the HR Cases wizard, the empty board and the Updates feed.
 *  Everything here restates what server/app/matcha/services/hr_cases does —
 *  change the two together. */

export const UPDATE_PREFIX = 'hr_case_'

/** Notices that put a case in HR's hands (the rest are "FYI, it moved"). */
export const NEEDS_YOU = new Set([
  'hr_case_flagged',
  'hr_case_draft_submitted',
  'hr_case_draft_held',
  'hr_case_signed_attention',
])

export const UPDATE_LABEL: Record<string, string> = {
  hr_case_flagged: 'Flagged',
  hr_case_draft_submitted: 'Write-up in',
  hr_case_draft_held: 'Held for HR',
  hr_case_approved: 'Approved',
  hr_case_changes_requested: 'Sent back',
  hr_case_delivered: 'Delivered',
  hr_case_signed_filed: 'Signed copy filed',
  hr_case_signed_attention: 'Needs a look',
}

export const thresholdPct = (threshold: number | undefined) => `${Math.round((threshold ?? 0.6) * 100)}%`

export type Trigger = { title: string; body: string }

export function triggers(threshold: number | undefined): Trigger[] {
  const pct = thresholdPct(threshold)
  return [
    {
      title: 'A new incident looks like a policy violation',
      body: `Every incident is read against your handbook and policies the moment it’s filed. At ${pct} confidence or higher, a case opens in New.`,
    },
    {
      title: 'An incident is closed',
      body: 'The same check runs again on close. A case you already closed or dismissed stays closed.',
    },
    {
      title: 'A manager sends in a write-up',
      body: 'From Write-ups, or by asking Huume. If no case exists for that incident yet, one opens with the letter already attached.',
    },
  ]
}

export type ColumnGuide = { acts: string; lands: string; empty: string }

export const COLUMN_GUIDE: Record<string, ColumnGuide> = {
  new: {
    acts: 'The manager',
    lands: 'Flagged by the handbook check, or waiting on the manager’s write-up. You can dismiss one with a reason.',
    empty: 'Nothing flagged. A case lands here when the handbook check finds a likely violation.',
  },
  review: {
    acts: 'You',
    lands: 'A write-up is in and has been checked. You approve it, or send it back with a reason of 20+ characters.',
    empty: 'Nothing waiting on you. Write-ups land here when a manager submits one.',
  },
  delivery: {
    acts: 'The manager',
    lands: 'Approved. The manager hands it to the employee and marks it delivered.',
    empty: 'Approved write-ups wait here until they’re delivered.',
  },
  signed: {
    acts: 'The manager, then Matcha',
    lands: 'The signed copy is filed in Drive and checked. It comes back to you only if the check finds a problem.',
    empty: 'Delivered write-ups wait here for their signed copy.',
  },
  done: {
    acts: 'No one',
    lands: 'Closed or dismissed in the last 30 days.',
    empty: 'Finished cases show here for 30 days.',
  },
}

export const NEEDS_YOU_MOMENTS: Trigger[] = [
  {
    title: 'A write-up is in',
    body: 'It’s been checked and is waiting in HR review. Approve it, or send it back with a reason.',
  },
  {
    title: 'A write-up is held',
    body: 'The protected-leave check found an overlap. It can’t be overridden, so it stays with you until the dates are fixed.',
  },
  {
    title: 'A signed copy has a problem',
    body: 'Unreadable, unsigned, wrong name, or the employee left comments. Comments and noted refusals always come to you.',
  },
]
