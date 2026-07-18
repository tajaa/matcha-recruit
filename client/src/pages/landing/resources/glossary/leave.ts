import type { GlossaryTerm } from './types'

export const GLOSSARY_LEAVE: GlossaryTerm[] = [
  {
    slug: 'fmla',
    term: 'Family and Medical Leave Act',
    abbreviation: 'FMLA',
    category: 'leave',
    short: 'Federal law providing up to 12 weeks of unpaid, job-protected leave per year for qualifying family/medical reasons.',
    definition:
      'FMLA (1993) entitles eligible employees of covered employers to take up to 12 weeks of unpaid, job-protected leave in a 12-month period for: birth/adoption, serious health condition of self or family member, or qualifying military exigency. Up to 26 weeks is available to care for a covered service member. Eligibility: employer has 50+ employees within 75 miles AND employee has worked 1,250+ hours over the past 12 months. Health insurance must be maintained during leave. Employer must restore the employee to the same or equivalent position.',
    related: ['leave', 'serious-health-condition', 'paid-family-leave'],
  },
  {
    slug: 'pto',
    term: 'Paid Time Off',
    abbreviation: 'PTO',
    category: 'leave',
    short: 'Employer-provided paid leave bank, often combining vacation, sick, and personal days.',
    definition:
      'PTO is not federally mandated, but many states/cities require paid sick leave specifically. Many states (CA, CO, MA, IL, NE, ND, etc.) treat accrued vacation/PTO as wages — meaning unused balances must be paid out at separation, "use-it-or-lose-it" forfeiture is illegal, and caps must be reasonable. Other states (NY, FL, TX) follow the employer\'s written policy.',
    related: ['paid-sick-leave', 'wage-payment', 'fmla'],
  },
  {
    slug: 'paid-family-leave',
    term: 'Paid Family Leave',
    abbreviation: 'PFL',
    category: 'leave',
    short: 'State-mandated paid leave for bonding, caregiving, or own serious health condition.',
    definition:
      'No federal PFL law exists. State PFL programs (CA, NJ, NY, RI, WA, MA, CT, OR, CO, MD, DE, ME, MN — list growing) typically replace 60–90% of wages for 8–12 weeks, funded by payroll deductions or employer/employee contributions, and run concurrently with FMLA where applicable. Eligibility, contribution rates, and benefit caps vary by state.',
    related: ['fmla', 'pto', 'pwfa'],
  },
]
