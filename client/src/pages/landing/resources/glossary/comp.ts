import type { GlossaryTerm } from './types'

export const GLOSSARY_COMP: GlossaryTerm[] = [
  {
    slug: 'minimum-wage',
    term: 'Minimum Wage',
    category: 'comp',
    short: 'The lowest hourly rate an employer can legally pay non-exempt employees.',
    definition:
      'Federal minimum wage is $7.25/hour (since 2009). Most states and many cities set higher minimums. The FLSA tipped minimum is $2.13/hour with a tip credit, but many states have eliminated or restricted the tip credit. Employers must pay the highest applicable minimum wage. Subminimum wages exist for limited categories (student learners, workers with disabilities under 14(c) certificates).',
    related: ['flsa', 'tip-credit', 'overtime'],
  },
]
