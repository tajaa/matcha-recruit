import type { GlossaryTerm } from './types'

export const GLOSSARY_CONCEPT: GlossaryTerm[] = [
  {
    slug: 'i-9',
    term: 'Form I-9',
    category: 'concept',
    short: 'Federal form verifying employment authorization for every new hire in the U.S.',
    definition:
      'Required by IRCA (1986) for every employee hired in the U.S. Section 1 must be completed by employee on or before first day; Section 2 by employer within 3 business days. Acceptable documents are listed on the form. Retain for 3 years after hire OR 1 year after termination, whichever is later. ICE audits result in significant per-form fines for paperwork errors. E-Verify is required for federal contractors and in some states.',
    related: ['e-verify', 'ircA', 'w-4'],
  },
  {
    slug: 'eeo-1',
    term: 'EEO-1 Component 1 Report',
    abbreviation: 'EEO-1',
    category: 'concept',
    short: 'Annual workforce demographic report required of employers with 100+ employees.',
    definition:
      'The EEO-1 Component 1 report categorizes employees by job category, race/ethnicity, and sex. Required of private employers with 100+ employees and federal contractors with 50+. Filed annually with the EEOC during a "data collection" window. Component 2 (pay data) was collected in 2017–2018 only.',
    related: ['eeoc', 'ofccp', 'title-vii'],
  },
  {
    slug: 'exempt',
    term: 'Exempt vs. Non-Exempt',
    category: 'concept',
    short: 'FLSA classification determining whether an employee is entitled to overtime.',
    definition:
      'Exempt employees are not entitled to FLSA overtime; non-exempt are. To be exempt, an employee must (1) be paid on a salary basis, (2) earn at least the federal threshold (currently $684/week, with state thresholds higher in CA, NY, WA), AND (3) primarily perform exempt duties (executive, administrative, professional, computer, outside sales). Job titles do not control — actual duties do. Misclassification is the most common FLSA violation.',
    related: ['flsa', 'overtime', 'misclassification'],
  },
  {
    slug: 'overtime',
    term: 'Overtime',
    category: 'concept',
    short: 'Premium pay (1.5×) for hours worked over 40 in a workweek under federal law.',
    definition:
      'FLSA requires non-exempt employees be paid 1.5× their regular rate for hours over 40 in a single workweek. The "regular rate" includes most non-discretionary bonuses, shift differentials, and commissions — not just hourly pay. Several states (CA, AK, NV, CO) require daily overtime after 8 hours. Comp time in lieu of overtime is generally illegal in the private sector.',
    related: ['flsa', 'exempt', 'regular-rate'],
  },
  {
    slug: 'at-will-employment',
    term: 'At-Will Employment',
    category: 'concept',
    short: 'Default U.S. employment doctrine: either party may terminate the relationship at any time, for any legal reason.',
    definition:
      'At-will means employment can be ended by either party at any time, with or without cause or notice — except where prohibited by law (discrimination, retaliation, public policy, contract). Montana is the only U.S. state that is not at-will (it requires good cause after a probationary period). Employers should avoid statements that create implied contracts ("permanent employment," "you have a job for life").',
    related: ['wrongful-termination', 'public-policy', 'constructive-discharge'],
  },
  {
    slug: 'wrongful-termination',
    term: 'Wrongful Termination',
    category: 'concept',
    short: 'Termination that violates a statute, contract, or public policy.',
    definition:
      'Even in at-will states, terminations are wrongful if they violate anti-discrimination law, retaliate for protected activity (whistleblowing, complaints, leave), breach an employment contract, or violate public policy (firing for jury duty, refusing to commit a crime). Documentation, consistent application of policy, and a clear non-discriminatory reason are key defenses.',
    related: ['at-will-employment', 'retaliation', 'public-policy'],
  },
  {
    slug: 'constructive-discharge',
    term: 'Constructive Discharge',
    category: 'concept',
    short: 'When an employee\'s resignation is treated as a termination because conditions were intolerable.',
    definition:
      'Constructive discharge occurs when an employer makes working conditions so intolerable that a reasonable person would feel compelled to resign — and does so. The resignation is then treated as a firing for legal purposes (e.g., enabling discrimination or retaliation claims). Examples: significant unjustified demotion, harassment that the employer fails to correct, drastic pay cuts.',
    related: ['wrongful-termination', 'hostile-work-environment'],
  },
  {
    slug: 'disparate-treatment',
    term: 'Disparate Treatment',
    category: 'concept',
    short: 'Intentional discrimination — treating someone less favorably because of a protected characteristic.',
    definition:
      'Disparate treatment is intentional discrimination based on a protected class (race, sex, age, etc.). Proven via direct evidence (e.g., a discriminatory comment) or the McDonnell Douglas burden-shifting framework: prima facie case → employer\'s legitimate non-discriminatory reason → plaintiff shows pretext.',
    related: ['title-vii', 'disparate-impact', 'pretext'],
  },
  {
    slug: 'disparate-impact',
    term: 'Disparate Impact',
    category: 'concept',
    short: 'A facially neutral policy that disproportionately harms a protected group.',
    definition:
      'Disparate impact occurs when a neutral policy or practice has a substantially adverse effect on a protected class. Intent is not required. Common examples: pre-employment tests, height/weight requirements, English-only rules, criminal-background bright-line bars. Defended by showing the practice is job-related and consistent with business necessity, with no less-discriminatory alternative.',
    related: ['title-vii', 'disparate-treatment', 'four-fifths-rule'],
  },
  {
    slug: 'hostile-work-environment',
    term: 'Hostile Work Environment',
    category: 'concept',
    short: 'Workplace harassment severe or pervasive enough to alter the conditions of employment.',
    definition:
      'A hostile work environment exists when unwelcome conduct based on a protected characteristic (sex, race, age, etc.) is severe or pervasive enough that a reasonable person would find it abusive. Single severe incidents (sexual assault, racial slurs) can suffice. Employers are liable for supervisor harassment unless the Faragher/Ellerth defense applies; for co-worker harassment, employers are liable if they knew or should have known and failed to act.',
    related: ['quid-pro-quo', 'retaliation', 'title-vii'],
  },
  {
    slug: 'quid-pro-quo',
    term: 'Quid Pro Quo Harassment',
    category: 'concept',
    short: 'Conditioning employment benefits on submission to unwelcome sexual conduct.',
    definition:
      'Quid pro quo ("this for that") sexual harassment occurs when a supervisor conditions a tangible employment action (hire, fire, promote, raise, assignment) on the employee\'s submission to sexual conduct. Single incidents create liability. Employers are strictly liable for supervisor quid-pro-quo harassment that results in a tangible employment action.',
    related: ['hostile-work-environment', 'title-vii'],
  },
  {
    slug: 'reasonable-accommodation',
    term: 'Reasonable Accommodation',
    category: 'concept',
    short: 'Modifications enabling qualified individuals to perform essential job functions.',
    definition:
      'Required under the ADA (disability), Title VII (religion), PWFA (pregnancy), and similar state laws. Employers must engage in an "interactive process" with the employee to identify effective accommodations unless doing so would cause undue hardship (significant difficulty or expense). Common accommodations: schedule changes, equipment, leave, telework, reassignment to a vacant position.',
    related: ['ada', 'pwfa', 'interactive-process', 'undue-hardship'],
  },
  {
    slug: 'retaliation',
    term: 'Retaliation',
    category: 'concept',
    short: 'Adverse action against an employee for engaging in protected activity.',
    definition:
      'Retaliation is the most-filed EEOC charge category. Protected activities include: opposing discrimination, filing a charge or complaint, participating in an investigation, requesting accommodations, taking FMLA leave, reporting safety violations, whistleblowing. The "adverse action" standard is broader than for discrimination — anything that might dissuade a reasonable employee from engaging in protected activity counts.',
    related: ['eeoc', 'protected-activity', 'wrongful-termination'],
  },
  {
    slug: 'protected-class',
    term: 'Protected Class',
    category: 'concept',
    short: 'Categories of people legally protected from discrimination.',
    definition:
      'Federal protected classes: race, color, religion, sex (incl. pregnancy, sexual orientation, gender identity per Bostock), national origin, age (40+), disability, genetic information, citizenship status, veteran status. State and local laws often add: marital status, sexual orientation/gender identity (where federal has gaps), arrest/conviction record, source of income, hairstyle (CROWN Act), height/weight (e.g., NYC, MI), and others.',
    related: ['title-vii', 'eeoc', 'crown-act'],
  },
  {
    slug: 'bfoq',
    term: 'Bona Fide Occupational Qualification',
    abbreviation: 'BFOQ',
    category: 'concept',
    short: 'Narrow exception allowing employment decisions based on a protected characteristic when reasonably necessary to the job.',
    definition:
      'A BFOQ permits discrimination on the basis of religion, sex, national origin, or age when the characteristic is reasonably necessary to the normal operation of the business — e.g., a Catholic school requiring teachers to be Catholic, an actor playing a specific gender. BFOQ does NOT exist for race or color under Title VII. Courts construe BFOQs very narrowly.',
    related: ['title-vii', 'protected-class'],
  },
  {
    slug: 'pip',
    term: 'Performance Improvement Plan',
    abbreviation: 'PIP',
    category: 'concept',
    short: 'Formal documented plan to address performance deficiencies with measurable goals and a defined timeframe.',
    definition:
      'A PIP outlines specific performance gaps, the standard expected, action steps, support provided, a review cadence, and a deadline (typically 30, 60, or 90 days). Done well, PIPs document the employer\'s legitimate non-discriminatory reason for any subsequent termination. Done badly (post-hoc, applied inconsistently, vague metrics), they are evidence of pretext.',
    related: ['progressive-discipline', 'wrongful-termination', 'documentation'],
  },
  {
    slug: 'misclassification',
    term: 'Worker Misclassification',
    category: 'concept',
    short: 'Incorrectly classifying employees as independent contractors or as exempt from overtime.',
    definition:
      'Two flavors: (1) classifying W-2 employees as 1099 contractors (avoiding payroll tax, OT, benefits) and (2) classifying non-exempt employees as exempt (avoiding OT). California\'s ABC test (AB 5) presumes employee status; the federal economic-realities test is multi-factor. Penalties include back wages, OT, taxes, benefits, and steep state penalties (CA Labor Code §226.8: $5K–$25K per misclassification).',
    related: ['1099', 'flsa', 'exempt'],
  },
]
