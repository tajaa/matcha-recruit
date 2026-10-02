/** The Sunday afternoon the week gets built — every section is one step of it,
 *  in order, ending at the 4:12 PM publish the hero animation stamps. */
export const STEPS = [
  { id: 'draft', time: '2:00', when: 'Sun 2:00 PM', label: 'Draft' },
  { id: 'check', time: '3:40', when: 'Sun 3:40 PM', label: 'Check' },
  { id: 'change', time: '3:58', when: 'Sun 3:58 PM', label: 'Change' },
  { id: 'cost', time: '4:05', when: 'Sun 4:05 PM', label: 'Cost' },
  { id: 'publish', time: '4:12', when: 'Sun 4:12 PM', label: 'Publish' },
] as const

/** The Incidents tab tells one case the same way: a Tuesday morning, from the
 *  report to the signed copy filed the next afternoon. */
export const INCIDENT_STEPS = [
  { id: 'report', time: '8:02', when: 'Tue 8:02 AM', label: 'Report' },
  { id: 'triage', time: '8:02', when: 'Tue 8:02 AM · +10 s', label: 'Triage' },
  { id: 'writeup', time: '8:40', when: 'Tue 8:40 AM', label: 'Write-up' },
  { id: 'approve', time: '9:15', when: 'Tue 9:15 AM', label: 'Approve' },
  { id: 'signed', time: '2:30', when: 'Wed 2:30 PM', label: 'Signed' },
] as const

export type StepDef = { id: string; time: string; when: string; label: string }
export type StepId = (typeof STEPS)[number]['id'] | (typeof INCIDENT_STEPS)[number]['id']
export const ALL_STEPS: readonly StepDef[] = [...STEPS, ...INCIDENT_STEPS]
export type LandingTab = 'scheduling' | 'incidents'
