/** The Sunday afternoon the week gets built — every section is one step of it,
 *  in order, ending at the 4:12 PM publish the hero animation stamps. */
export const STEPS = [
  { id: 'draft', time: '2:00', label: 'Draft' },
  { id: 'check', time: '3:40', label: 'Check' },
  { id: 'change', time: '3:58', label: 'Change' },
  { id: 'cost', time: '4:05', label: 'Cost' },
  { id: 'publish', time: '4:12', label: 'Publish' },
] as const

export type StepId = (typeof STEPS)[number]['id']
