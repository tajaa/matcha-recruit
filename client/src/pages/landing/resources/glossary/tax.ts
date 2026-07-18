import type { GlossaryTerm } from './types'

export const GLOSSARY_TAX: GlossaryTerm[] = [
  {
    slug: 'w-2',
    term: 'Form W-2',
    category: 'tax',
    short: 'Annual wage and tax statement issued by employers to employees.',
    definition:
      'IRS Form W-2 reports an employee\'s annual wages and tax withholding. Must be furnished to employees and filed with the SSA by January 31 of the following year. Reports federal/state/local income tax withheld, Social Security and Medicare wages, and various box codes (401(k), HSA, third-party sick pay, etc.).',
    related: ['w-4', 'fica', '1099'],
  },
  {
    slug: 'w-4',
    term: 'Form W-4',
    category: 'tax',
    short: 'Employee\'s federal income tax withholding certificate.',
    definition:
      'IRS Form W-4 tells employers how much federal income tax to withhold from an employee\'s paycheck. Redesigned in 2020 to remove allowances. Employees can update at any time. Many states have separate state withholding forms (e.g., DE 4 in CA, IT-2104 in NY).',
    related: ['w-2', 'i-9', 'fica'],
  },
  {
    slug: '1099',
    term: 'Form 1099-NEC / Independent Contractor',
    category: 'tax',
    short: 'Tax form for non-employee compensation paid to independent contractors.',
    definition:
      'Form 1099-NEC reports payments of $600+ to non-employees. Misclassification of workers as 1099 contractors when they should be W-2 employees is a major source of legal and tax liability. The IRS uses a multi-factor common-law test; California uses the strict ABC test (AB 5); the DOL has its own economic-realities test. Penalties include back wages, overtime, taxes, and benefits.',
    related: ['w-2', 'flsa', 'misclassification'],
  },
  {
    slug: 'fica',
    term: 'Federal Insurance Contributions Act',
    abbreviation: 'FICA',
    category: 'tax',
    short: 'Federal payroll tax funding Social Security and Medicare.',
    definition:
      'FICA imposes a 6.2% Social Security tax (up to a wage base limit) and 1.45% Medicare tax on wages, with matching employer contributions. An additional 0.9% Medicare tax applies to wages over $200,000 (employee-only). Self-employed individuals pay both halves via SECA.',
    related: ['w-2', 'futa', 'suta'],
  },
  {
    slug: 'futa',
    term: 'Federal Unemployment Tax Act',
    abbreviation: 'FUTA',
    category: 'tax',
    short: 'Federal payroll tax funding the federal portion of unemployment insurance.',
    definition:
      'FUTA imposes a 6.0% tax on the first $7,000 of each employee\'s wages. Most employers receive a 5.4% credit for paying state unemployment taxes (SUTA), reducing the effective rate to 0.6%. Reported on Form 940 annually.',
    related: ['suta', 'fica', 'unemployment'],
  },
  {
    slug: 'suta',
    term: 'State Unemployment Tax Act',
    abbreviation: 'SUTA',
    category: 'tax',
    short: 'State payroll tax funding state unemployment insurance benefits.',
    definition:
      'Each state runs its own unemployment insurance program funded by employer payroll taxes. Rates vary by state and by employer experience rating (claims history). New employers pay a state-set new-employer rate. SUTA dumping (manipulating ratings via shell companies) is a federal crime.',
    related: ['futa', 'unemployment'],
  },
]
