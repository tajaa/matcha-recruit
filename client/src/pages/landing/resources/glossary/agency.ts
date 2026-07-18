import type { GlossaryTerm } from './types'

export const GLOSSARY_AGENCY: GlossaryTerm[] = [
  {
    slug: 'eeoc',
    term: 'Equal Employment Opportunity Commission',
    abbreviation: 'EEOC',
    category: 'agency',
    short: 'Federal agency enforcing laws against workplace discrimination.',
    definition:
      'The EEOC enforces federal laws prohibiting employment discrimination based on race, color, religion, sex, national origin, age (40+), disability, or genetic information. It investigates charges, issues right-to-sue letters, and may file suit on behalf of complainants. Employers with 15+ employees (20+ for ADEA) are covered. Most charges must be filed within 180 days (300 in deferral states). Required to file annual EEO-1 reports if 100+ employees (or 50+ for federal contractors).',
    related: ['title-vii', 'eeo-1', 'adea', 'ada'],
  },
  {
    slug: 'osha',
    term: 'Occupational Safety and Health Administration',
    abbreviation: 'OSHA',
    category: 'agency',
    short: 'Federal agency setting and enforcing workplace safety standards.',
    definition:
      'OSHA enforces standards under the Occupational Safety and Health Act (1970). Covered employers must provide a workplace free from recognized hazards, comply with industry-specific standards, post the OSHA poster, maintain Form 300 injury logs, and report fatalities (within 8 hours) and serious injuries (within 24 hours). Many states run their own OSHA-approved plans (Cal/OSHA, MIOSHA, etc.) which may be more stringent.',
    related: ['form-300', 'safety', 'workers-comp'],
  },
  {
    slug: 'dol',
    term: 'Department of Labor',
    abbreviation: 'DOL',
    category: 'agency',
    short: 'Federal cabinet department enforcing wage, hour, leave, and benefits laws.',
    definition:
      'The DOL houses the Wage and Hour Division (FLSA, FMLA), OSHA (safety), OFCCP (federal contractor compliance), EBSA (ERISA/benefits), VETS (USERRA), and others. The Wage and Hour Division handles most FLSA and FMLA enforcement, including investigations, back-wage recovery, and audits.',
    related: ['flsa', 'fmla', 'ofccp'],
  },
  {
    slug: 'nlrb',
    term: 'National Labor Relations Board',
    abbreviation: 'NLRB',
    category: 'agency',
    short: 'Federal agency enforcing the National Labor Relations Act and union election rules.',
    definition:
      'The NLRB enforces the NLRA, which protects employees\' rights to engage in protected concerted activity (discussing wages, working conditions, or organizing) — even in non-union workplaces. Common employer pitfalls: overly broad social media or confidentiality policies, interrogating employees about union activity, retaliating against organizers. Penalties include reinstatement and back pay.',
    related: ['nlra', 'protected-concerted-activity', 'union'],
  },
  {
    slug: 'ofccp',
    term: 'Office of Federal Contract Compliance Programs',
    abbreviation: 'OFCCP',
    category: 'agency',
    short: 'DOL agency enforcing affirmative-action and non-discrimination obligations of federal contractors.',
    definition:
      'OFCCP enforces Executive Order 11246, Section 503 (disability), and VEVRAA (veterans) for federal contractors. Contractors with 50+ employees and a $50,000+ contract must develop written affirmative action programs (AAPs). Audits review hiring data, compensation analyses, and outreach.',
    related: ['eeoc', 'eeo-1', 'aap'],
  },
]
