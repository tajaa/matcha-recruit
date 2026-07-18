export const SUITES = ['completeness', 'tagging', 'golden', 'authority', 'baseline'] as const
export type Suite = (typeof SUITES)[number]

export const INDUSTRIES = [
  'manufacturing',
  'healthcare',
  'healthcare:oncology',
  'biotech',
  'hospitality',
  'retail',
  'technology',
  'fast food',
]

/** Industries with a curated <=30-key must-have checklist. Others only have the full sweep. */
export const CORE_INDUSTRIES = new Set(['manufacturing', 'healthcare'])
