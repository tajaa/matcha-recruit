import type { GlossaryTerm } from './types'

export const CATEGORIES_LABEL: Record<GlossaryTerm['category'], string> = {
  law: 'Federal/State Law',
  agency: 'Agency',
  concept: 'Concept',
  tax: 'Tax',
  leave: 'Leave',
  comp: 'Compensation',
}
