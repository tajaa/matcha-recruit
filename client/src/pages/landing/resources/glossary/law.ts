import type { GlossaryTerm } from './types'

export const GLOSSARY_LAW: GlossaryTerm[] = [
  {
    slug: 'flsa',
    term: 'Fair Labor Standards Act',
    abbreviation: 'FLSA',
    category: 'law',
    short: 'Federal law setting minimum wage, overtime, recordkeeping, and child-labor standards.',
    definition:
      'The FLSA (1938) requires non-exempt employees be paid at least the federal minimum wage and overtime at 1.5× regular rate for hours over 40 in a workweek. It defines exempt vs. non-exempt classifications, regulates child labor, and mandates time + pay records. State law can be more protective (higher minimum wage, daily overtime). Misclassification of employees as exempt or as 1099 contractors is the most common FLSA violation and a frequent source of class-action lawsuits.',
    related: ['exempt', 'overtime', 'minimum-wage', 'dol'],
  },
  {
    slug: 'ada',
    term: 'Americans with Disabilities Act',
    abbreviation: 'ADA',
    category: 'law',
    short: 'Federal law prohibiting discrimination on the basis of disability in employment, public services, and accommodations.',
    definition:
      'Title I of the ADA (1990, amended 2008 as ADAAA) prohibits employers with 15+ employees from discriminating against qualified individuals with disabilities and requires reasonable accommodations unless doing so would cause undue hardship. The 2008 amendments significantly broadened the definition of "disability." Common accommodations: modified schedules, assistive technology, accessible workspaces, leave beyond FMLA, reassignment. Employers must engage in an interactive process to identify accommodations.',
    related: ['reasonable-accommodation', 'interactive-process', 'eeoc'],
  },
  {
    slug: 'adaaa',
    term: 'ADA Amendments Act',
    abbreviation: 'ADAAA',
    category: 'law',
    short: '2008 amendments that significantly broadened the definition of "disability" under the ADA.',
    definition:
      'The ADAAA reversed restrictive Supreme Court rulings and clarified that the definition of disability should be construed broadly. Mitigating measures (medication, hearing aids, prosthetics) are no longer considered when determining if someone has a disability. Episodic conditions and conditions in remission qualify if they would substantially limit a major life activity when active.',
    related: ['ada', 'reasonable-accommodation'],
  },
  {
    slug: 'aca',
    term: 'Affordable Care Act',
    abbreviation: 'ACA',
    category: 'law',
    short: 'Federal law (2010) reforming health insurance, including the employer mandate for groups with 50+ FTEs.',
    definition:
      'The ACA requires Applicable Large Employers (50+ full-time-equivalent employees) to offer affordable, minimum-value health coverage to full-time employees (30+ hours/week) and their dependents, or pay a penalty. Employers must report coverage offers via Forms 1094-C / 1095-C. Other provisions: dependent coverage to age 26, no pre-existing-condition exclusions, preventive care without cost-sharing.',
    related: ['ale', 'cobra', 'erisa'],
  },
  {
    slug: 'cobra',
    term: 'Consolidated Omnibus Budget Reconciliation Act',
    abbreviation: 'COBRA',
    category: 'law',
    short: 'Federal law allowing employees and dependents to continue group health coverage after a qualifying event.',
    definition:
      'COBRA (1985) requires employers with 20+ employees to offer continuation of group health coverage for up to 18 months (or 36 in some cases) after qualifying events like termination, reduction of hours, divorce, or death. The covered person pays the full premium plus a 2% admin fee. Employers must send a COBRA election notice within 14 days of notification of a qualifying event. Many states have "mini-COBRA" laws covering smaller employers.',
    related: ['aca', 'erisa', 'qualifying-event'],
  },
  {
    slug: 'hipaa',
    term: 'Health Insurance Portability and Accountability Act',
    abbreviation: 'HIPAA',
    category: 'law',
    short: 'Federal law protecting the privacy and security of individually identifiable health information.',
    definition:
      'HIPAA (1996) governs how protected health information (PHI) is used and disclosed by covered entities and their business associates. For HR: medical information collected for FMLA, ADA, workers\' comp, or wellness programs must be kept in separate, confidential files — not in personnel files. Health plan information is also subject to HIPAA. Violations can carry significant civil and criminal penalties.',
    related: ['phi', 'fmla', 'ada'],
  },
  {
    slug: 'title-vii',
    term: 'Title VII of the Civil Rights Act',
    abbreviation: 'Title VII',
    category: 'law',
    short: 'Federal law prohibiting employment discrimination based on race, color, religion, sex, or national origin.',
    definition:
      'Title VII (1964) is the foundational federal anti-discrimination employment law. Covers employers with 15+ employees. Prohibits discrimination in hiring, firing, pay, promotion, training, and any other term or condition of employment. Bostock v. Clayton County (2020) extended "sex" to include sexual orientation and gender identity. Religious accommodation must be provided unless undue hardship.',
    related: ['eeoc', 'disparate-impact', 'disparate-treatment', 'protected-class'],
  },
  {
    slug: 'adea',
    term: 'Age Discrimination in Employment Act',
    abbreviation: 'ADEA',
    category: 'law',
    short: 'Federal law protecting workers age 40+ from age-based discrimination.',
    definition:
      'ADEA (1967) prohibits age-based discrimination against employees and applicants 40 or older. Covers employers with 20+ employees. Includes prohibitions on age-based job ads, mandatory retirement (with limited exceptions), and disparate-impact policies. Reductions in force (RIFs) are a common ADEA risk area; OWBPA-compliant releases are required for waivers of ADEA claims.',
    related: ['title-vii', 'owbpa', 'eeoc'],
  },
  {
    slug: 'owbpa',
    term: 'Older Workers Benefit Protection Act',
    abbreviation: 'OWBPA',
    category: 'law',
    short: 'Federal law setting strict requirements for waivers of age-discrimination claims (e.g., severance agreements).',
    definition:
      'OWBPA amends the ADEA to require that any waiver of age-discrimination claims be "knowing and voluntary." Requirements: written in plain language, advise employee to consult counsel, provide 21 days to consider (45 for group layoffs), 7-day revocation period after signing, and (for group RIFs) disclose the job titles + ages of those selected and not selected. Non-compliant waivers are invalid even if the employee already cashed the severance check.',
    related: ['adea', 'rif', 'severance'],
  },
  {
    slug: 'gina',
    term: 'Genetic Information Nondiscrimination Act',
    abbreviation: 'GINA',
    category: 'law',
    short: 'Federal law prohibiting employers from using genetic information in employment decisions.',
    definition:
      'GINA (2008) prohibits employers (15+ employees) from requesting, requiring, or using genetic information — including family medical history — in any employment decision. Wellness program design, fitness-for-duty exams, and post-offer medical questionnaires are common compliance trip-wires. Safe-harbor language is required when requesting medical information.',
    related: ['ada', 'eeoc', 'wellness-program'],
  },
  {
    slug: 'pda',
    term: 'Pregnancy Discrimination Act',
    abbreviation: 'PDA',
    category: 'law',
    short: 'Federal law amending Title VII to prohibit discrimination based on pregnancy, childbirth, or related conditions.',
    definition:
      'The PDA (1978) requires employers to treat pregnancy and pregnancy-related conditions the same as any other temporary disability. Combined with the PWFA (Pregnant Workers Fairness Act, effective 2023) and PUMP Act, employers must accommodate pregnancy, childbirth, and lactation needs.',
    related: ['pwfa', 'pump-act', 'title-vii'],
  },
  {
    slug: 'pwfa',
    term: 'Pregnant Workers Fairness Act',
    abbreviation: 'PWFA',
    category: 'law',
    short: 'Federal law (2023) requiring reasonable accommodations for pregnancy, childbirth, and related conditions.',
    definition:
      'PWFA, effective June 2023, requires covered employers (15+) to provide reasonable accommodations for known limitations related to pregnancy, childbirth, or related medical conditions, unless doing so would cause undue hardship. Covers temporary suspension of essential job functions — broader than the ADA standard.',
    related: ['pda', 'pump-act', 'reasonable-accommodation'],
  },
  {
    slug: 'pump-act',
    term: 'PUMP for Nursing Mothers Act',
    abbreviation: 'PUMP Act',
    category: 'law',
    short: 'Federal law expanding break-time and private-space protections for nursing employees.',
    definition:
      'The PUMP Act (2022) extends FLSA Section 7(r) lactation accommodation requirements to most non-exempt and exempt employees for up to one year after childbirth. Requires reasonable break time and a private (non-bathroom) space free from intrusion. Small-employer (under 50) undue-hardship exemption applies in narrow cases.',
    related: ['pwfa', 'pda', 'flsa'],
  },
  {
    slug: 'erisa',
    term: 'Employee Retirement Income Security Act',
    abbreviation: 'ERISA',
    category: 'law',
    short: 'Federal law setting minimum standards for private-sector retirement and welfare benefit plans.',
    definition:
      'ERISA (1974) governs most employer-sponsored retirement plans (401(k), pension) and welfare benefit plans (health, disability, life). Imposes fiduciary duties on plan sponsors, requires summary plan descriptions (SPDs), 5500 filings, and grants participants the right to sue. Pre-empts most state laws affecting covered plans.',
    related: ['401k', 'aca', 'cobra'],
  },
  {
    slug: 'fcra',
    term: 'Fair Credit Reporting Act',
    abbreviation: 'FCRA',
    category: 'law',
    short: 'Federal law regulating background checks and consumer reports used in employment decisions.',
    definition:
      'FCRA requires employers using third-party background checks to: (1) provide a clear and conspicuous standalone disclosure, (2) get written authorization, (3) provide a pre-adverse-action notice with a copy of the report and "A Summary of Your Rights," before taking adverse action, and (4) provide a final adverse-action notice afterward. Class actions over disclosure-form defects are extremely common.',
    related: ['ban-the-box', 'background-check', 'adverse-action'],
  },
  {
    slug: 'warn',
    term: 'Worker Adjustment and Retraining Notification Act',
    abbreviation: 'WARN',
    category: 'law',
    short: 'Federal law requiring 60 days\' notice for mass layoffs and plant closings.',
    definition:
      'WARN requires employers with 100+ full-time employees to give 60 calendar days\' advance written notice of a "plant closing" (50+ losses at a single site) or "mass layoff" (50+ if a third of the workforce, or 500+ regardless). Several states have stricter mini-WARN laws (CA, NY, NJ, IL). Violations require pay + benefits for the notice shortfall.',
    related: ['rif', 'severance'],
  },
  {
    slug: 'userra',
    term: 'Uniformed Services Employment and Reemployment Rights Act',
    abbreviation: 'USERRA',
    category: 'law',
    short: 'Federal law protecting employment rights of military service members.',
    definition:
      'USERRA prohibits discrimination based on military service and requires employers to reemploy returning service members in the same or equivalent position with seniority and benefits as if they had been continuously employed (the "escalator principle"). Covers up to 5 cumulative years of service. Health coverage continuation is required for up to 24 months.',
    related: ['leave', 'reemployment'],
  },
  {
    slug: 'ban-the-box',
    term: 'Ban the Box',
    category: 'law',
    short: 'Laws prohibiting criminal-history questions on initial job applications.',
    definition:
      '"Ban the box" laws prohibit employers from asking about criminal history on the initial application — and often delay the inquiry until after a conditional offer. 37+ states and 150+ localities have ban-the-box laws covering some or all employers. The federal Fair Chance Act covers federal contractors. Even where allowed, blanket bans on hiring people with records can violate Title VII via disparate impact.',
    related: ['fcra', 'fair-chance-act', 'eeoc'],
  },
  {
    slug: 'crown-act',
    term: 'CROWN Act',
    category: 'law',
    short: 'State laws prohibiting discrimination based on natural hair texture and protective hairstyles.',
    definition:
      'The CROWN Act (Creating a Respectful and Open World for Natural Hair) prohibits discrimination based on hair texture and protective styles (braids, locs, twists, knots) historically associated with race. Enacted in 25+ states and many cities. Grooming and dress-code policies must accommodate these styles unless a narrow safety justification applies.',
    related: ['title-vii', 'protected-class'],
  },
  {
    slug: 'pay-transparency',
    term: 'Pay Transparency',
    category: 'law',
    short: 'Laws requiring employers to disclose pay ranges in job postings and/or to applicants and employees.',
    definition:
      'Pay-transparency laws require employers to disclose pay ranges. Coverage varies by jurisdiction: CA, CO, WA, NY, IL (effective 2025), DC, and several cities (NYC, Jersey City, Cincinnati, Toledo, Ithaca) require pay ranges in job postings. Other states require disclosure on request or upon offer. Penalties for non-compliance include fines per posting and DOL audits.',
    related: ['equal-pay-act', 'minimum-wage'],
  },
  {
    slug: 'equal-pay-act',
    term: 'Equal Pay Act',
    abbreviation: 'EPA',
    category: 'law',
    short: 'Federal law requiring equal pay for equal work regardless of sex.',
    definition:
      'The EPA (1963) prohibits sex-based wage discrimination for substantially equal work in the same establishment, defined by skill, effort, responsibility, and similar working conditions. Employers can defend pay differences only via (1) seniority, (2) merit, (3) quantity/quality of production, or (4) any factor other than sex. Many state EPAs are stricter — banning use of salary history (CA, MA, NY, etc.) and requiring equal pay for "substantially similar" or "comparable" work.',
    related: ['pay-transparency', 'title-vii', 'salary-history-ban'],
  },
]
