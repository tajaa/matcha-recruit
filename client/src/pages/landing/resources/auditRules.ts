export type Severity = 'high' | 'medium' | 'low'

export type AuditQuestion = {
  id: string
  category: string
  question: string
  helper?: string
  severity: Severity
  /** When the answer is "no" the gap fires; when "yes" it's clear. */
  gap: { title: string; detail: string }
}

export type AuditAnswer = 'yes' | 'no' | 'unsure'

export type Finding = {
  id: string
  severity: Severity
  category: string
  title: string
  detail: string
}

export const INDUSTRIES = [
  'Healthcare',
  'Hospitality',
  'Retail',
  'Manufacturing',
  'Construction',
  'Professional services',
  'Tech / SaaS',
  'Non-profit',
  'Other',
] as const

export const QUESTIONS: AuditQuestion[] = [
  {
    id: 'posters',
    category: 'Posting Requirements',
    severity: 'medium',
    question: 'Do you display all required federal and state labor posters at every work location?',
    helper: 'FLSA, FMLA, OSHA, EEOC, USERRA, plus state minimum wage, sick leave, and pay transparency posters.',
    gap: {
      title: 'Missing required workplace posters',
      detail:
        'Federal posters (FLSA, FMLA, OSHA, EEOC, USERRA) and state-specific posters must be physically posted at every location. Remote employees need digital equivalents. DOL fines run up to $39,800 per violation for repeat or willful infractions.',
    },
  },
  {
    id: 'handbook',
    category: 'Policies',
    severity: 'high',
    question: 'Do you have a written employee handbook that has been reviewed in the last 12 months?',
    helper: 'Pay-transparency, AI-in-hiring, and sick-leave laws change yearly across multiple states.',
    gap: {
      title: 'Stale or missing employee handbook',
      detail:
        'A handbook older than 12 months almost certainly misses recent state law changes (CA pay transparency, IL pay transparency, NY AI-in-hiring, expanded sick-leave laws, CROWN Act updates, etc.). Outdated handbooks can affirmatively create liability.',
    },
  },
  {
    id: 'i9',
    category: 'Hiring',
    severity: 'high',
    question: 'Do you complete Form I-9 within 3 business days for every new hire?',
    helper: 'Required by IRCA. Section 1 by employee on or before day 1; Section 2 by employer within 3 business days.',
    gap: {
      title: 'I-9 completion gap',
      detail:
        'ICE penalties for I-9 paperwork violations run from ~$281 to ~$2,789 per form. Even technical errors (wrong document listed, missing signature, late completion) trigger fines. Conduct an internal I-9 audit using the DOJ-OSC self-audit guidance.',
    },
  },
  {
    id: 'pto-policy',
    category: 'Leave',
    severity: 'high',
    question: 'Do you have written PTO and/or sick leave policies that comply with each state where you operate?',
    helper: 'CA, CO, MA, IL, NE, ND treat accrued PTO as wages. Many states/cities mandate paid sick leave separately from PTO.',
    gap: {
      title: 'PTO / sick leave policy compliance',
      detail:
        'In wages-states, "use it or lose it" forfeiture is illegal and accrued balances must be paid out at separation. Many states (CA, CO, MA, MD, NJ, NM, NV, NY, OR, RI, VT, WA + ~30 cities) require paid sick leave separate from PTO. Single nationwide PTO policies almost always violate at least one state law.',
    },
  },
  {
    id: 'classification',
    category: 'Worker Classification',
    severity: 'high',
    question: 'Do you classify workers (1099 contractors and exempt-vs-non-exempt) using current legal tests for every state you operate in?',
    helper: 'CA uses the strict ABC test (AB 5). Federal DOL uses an economic-realities test. NY, NJ, MA each have their own rules.',
    gap: {
      title: 'Worker misclassification risk',
      detail:
        'Misclassifying employees as 1099 contractors or as exempt-from-overtime is the most expensive HR mistake. Liability includes back wages, overtime, taxes, benefits, and stiff state penalties (CA Labor Code §226.8 alone: $5K–$25K per misclassification). Re-audit classifications annually and on each new state.',
    },
  },
  {
    id: 'harassment-training',
    category: 'Anti-Harassment',
    severity: 'medium',
    question: 'Do you have a documented anti-harassment policy AND provide the harassment training required in each state?',
    helper: 'CA, CT, DE, IL, ME, NY, WA require sexual-harassment training; cadence and duration vary by state.',
    gap: {
      title: 'Harassment policy or training gap',
      detail:
        'A written, distributed anti-harassment policy is your first defense in any harassment claim. CA (every 2 years, 1-2 hours), IL (annual), NY (annual), CT, DE, ME, WA all mandate training with state-specific content. Missing or expired training removes the Faragher/Ellerth affirmative defense.',
    },
  },
  {
    id: 'medical-files',
    category: 'Records',
    severity: 'medium',
    question: 'Do you keep medical, FMLA, ADA, and workers\' comp records in separate files from personnel files?',
    helper: 'Required by ADA, HIPAA, and GINA — medical info cannot live in the personnel file.',
    gap: {
      title: 'Medical record segregation',
      detail:
        'ADA, HIPAA, and GINA all require medical information be kept separate from personnel files, with access restricted to those with a legitimate need. Genetic info (incl. family medical history) requires its own additional segregation under GINA.',
    },
  },
  {
    id: 'new-hire-notices',
    category: 'Hiring',
    severity: 'medium',
    question: 'Do you provide all state-required new-hire notices (wage notices, paid leave, workers\' comp, etc.) on or before day 1?',
    helper: 'CA Wage Theft Notice (Labor Code 2810.5), NY WTPA, MA Paid Family Leave notice, etc.',
    gap: {
      title: 'New-hire notice compliance',
      detail:
        'Most states require specific written notices at hire (wage rate, pay schedule, employer info, paid leave eligibility, workers\' comp, EEO). Some carry per-employee penalties (CA WTPA: $100/employee for first violation, $200 thereafter). NY WTPA: $50/week up to $5,000/employee.',
    },
  },
  {
    id: 'final-paycheck',
    category: 'Termination',
    severity: 'high',
    question: 'Do you have written termination procedures that include final paycheck timing for each state?',
    helper: 'CA: same day for involuntary, 72 hours for voluntary. MA: same day. Other states vary widely.',
    gap: {
      title: 'Final paycheck procedure',
      detail:
        'Final paycheck timing varies wildly: CA pays involuntary terms same day (incl. accrued vacation); MA pays same day; many states allow next regular payday; others have 24/48/72-hour windows. Late final paychecks trigger waiting-time penalties — CA waiting-time penalty alone can reach 30 days of wages.',
    },
  },
  {
    id: 'background-checks',
    category: 'Hiring',
    severity: 'medium',
    question: 'Do you conduct background checks following FCRA requirements (standalone disclosure, written consent, pre-adverse-action notice)?',
    helper: 'Plus 37+ states with "ban the box" laws delaying when criminal history can be asked.',
    gap: {
      title: 'FCRA + ban-the-box compliance',
      detail:
        'FCRA requires (1) standalone written disclosure, (2) written authorization, (3) pre-adverse-action notice with copy of report + Summary of Rights, (4) final adverse-action notice. Defective disclosure forms drive massive class-action settlements. Plus 37+ ban-the-box states/150+ cities restrict when criminal history can be requested.',
    },
  },
  {
    id: 'pay-transparency',
    category: 'Compensation',
    severity: 'medium',
    question: 'Do your job postings comply with pay-transparency laws in every state where you post?',
    helper: 'CA, CO, WA, NY, IL (2025), DC require pay ranges in postings. NYC, Jersey City, and others too.',
    gap: {
      title: 'Pay transparency on job postings',
      detail:
        'CA, CO, WA, NY, IL (effective 2025), DC require pay ranges in job postings; remote-friendly postings can pull employers into multiple state regimes. Missing ranges trigger fines per posting (CO: $500–$10,000 per violation; NY: $1,000–$3,000) and increasingly fuel pay-discrimination claims.',
    },
  },
  {
    id: 'pump-act',
    category: 'Leave',
    severity: 'medium',
    question: 'Do you provide private (non-bathroom) lactation space and reasonable break time for nursing employees up to 1 year postpartum?',
    helper: 'Required by the federal PUMP Act (2022) for almost all employees, exempt and non-exempt.',
    gap: {
      title: 'PUMP Act lactation accommodation',
      detail:
        'The PUMP Act (2022) extended lactation break requirements to virtually all employees (exempt + non-exempt) for up to 1 year after childbirth. Requires reasonable break time and a private, non-bathroom space free from intrusion. Several states require additional accommodations (CA: pump-room standards; OR: paid breaks).',
    },
  },
]

export function computeFindings(answers: Record<string, AuditAnswer>): Finding[] {
  const out: Finding[] = []
  for (const q of QUESTIONS) {
    const a = answers[q.id]
    // "no" or "unsure" both fire as gaps; unsure downgraded to medium severity if it was high
    if (a === 'no' || a === 'unsure') {
      out.push({
        id: q.id,
        severity: a === 'unsure' && q.severity === 'high' ? 'medium' : q.severity,
        category: q.category,
        title: q.gap.title,
        detail: q.gap.detail,
      })
    }
  }
  return out
}

export function computeScore(answers: Record<string, AuditAnswer>): { score: number; answered: number; total: number } {
  const total = QUESTIONS.length
  let yes = 0
  let answered = 0
  for (const q of QUESTIONS) {
    const a = answers[q.id]
    if (a) answered += 1
    if (a === 'yes') yes += 2
    else if (a === 'unsure') yes += 1
  }
  const maxPoints = total * 2
  const score = Math.round((yes / maxPoints) * 100)
  return { score, answered, total }
}
