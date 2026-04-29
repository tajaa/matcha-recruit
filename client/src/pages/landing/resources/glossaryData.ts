export type GlossaryTerm = {
  slug: string
  term: string
  abbreviation?: string
  short: string
  definition: string
  related?: string[]
  category: 'law' | 'agency' | 'concept' | 'tax' | 'leave' | 'comp'
}

export const GLOSSARY: GlossaryTerm[] = [
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
    slug: 'i-9',
    term: 'Form I-9',
    category: 'concept',
    short: 'Federal form verifying employment authorization for every new hire in the U.S.',
    definition:
      'Required by IRCA (1986) for every employee hired in the U.S. Section 1 must be completed by employee on or before first day; Section 2 by employer within 3 business days. Acceptable documents are listed on the form. Retain for 3 years after hire OR 1 year after termination, whichever is later. ICE audits result in significant per-form fines for paperwork errors. E-Verify is required for federal contractors and in some states.',
    related: ['e-verify', 'ircA', 'w-4'],
  },
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
    slug: 'ofccp',
    term: 'Office of Federal Contract Compliance Programs',
    abbreviation: 'OFCCP',
    category: 'agency',
    short: 'DOL agency enforcing affirmative-action and non-discrimination obligations of federal contractors.',
    definition:
      'OFCCP enforces Executive Order 11246, Section 503 (disability), and VEVRAA (veterans) for federal contractors. Contractors with 50+ employees and a $50,000+ contract must develop written affirmative action programs (AAPs). Audits review hiring data, compensation analyses, and outreach.',
    related: ['eeoc', 'eeo-1', 'aap'],
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
    slug: 'minimum-wage',
    term: 'Minimum Wage',
    category: 'comp',
    short: 'The lowest hourly rate an employer can legally pay non-exempt employees.',
    definition:
      'Federal minimum wage is $7.25/hour (since 2009). Most states and many cities set higher minimums. The FLSA tipped minimum is $2.13/hour with a tip credit, but many states have eliminated or restricted the tip credit. Employers must pay the highest applicable minimum wage. Subminimum wages exist for limited categories (student learners, workers with disabilities under 14(c) certificates).',
    related: ['flsa', 'tip-credit', 'overtime'],
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
    slug: 'ban-the-box',
    term: 'Ban the Box',
    category: 'law',
    short: 'Laws prohibiting criminal-history questions on initial job applications.',
    definition:
      '"Ban the box" laws prohibit employers from asking about criminal history on the initial application — and often delay the inquiry until after a conditional offer. 37+ states and 150+ localities have ban-the-box laws covering some or all employers. The federal Fair Chance Act covers federal contractors. Even where allowed, blanket bans on hiring people with records can violate Title VII via disparate impact.',
    related: ['fcra', 'fair-chance-act', 'eeoc'],
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

export const CATEGORIES_LABEL: Record<GlossaryTerm['category'], string> = {
  law: 'Federal/State Law',
  agency: 'Agency',
  concept: 'Concept',
  tax: 'Tax',
  leave: 'Leave',
  comp: 'Compensation',
}
