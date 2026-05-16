/**
 * Security Survey question bank.
 *
 * Static checklist consumed by `IRSecuritySurveyTab`. Keep `id` values
 * stable — they are persisted in `ir_surveys.responses` JSONB and used
 * to look up historical answers when viewing past surveys.
 */

export interface Question {
  id: string
  text: string
}

export interface Category {
  id: string
  label: string
  questions: Question[]
}

export const SURVEY_CATEGORIES: Category[] = [
  {
    id: 'physical',
    label: 'Physical Security',
    questions: [
      { id: 'p1', text: 'Exterior lighting is adequate at all entrances and parking areas' },
      { id: 'p2', text: 'Security cameras are installed and operational' },
      { id: 'p3', text: 'Access control system is in place (key cards, codes, or similar)' },
      { id: 'p4', text: 'All exterior doors have functioning, secure locks' },
      { id: 'p5', text: 'Visitor sign-in/sign-out procedure is enforced' },
    ],
  },
  {
    id: 'emergency',
    label: 'Emergency Preparedness',
    questions: [
      { id: 'e1', text: 'Evacuation plan is posted in multiple visible locations' },
      { id: 'e2', text: 'Emergency contact list is accessible to all employees' },
      { id: 'e3', text: 'First aid kits are fully stocked and accessible' },
      { id: 'e4', text: 'Fire extinguishers are inspected, current, and accessible' },
      { id: 'e5', text: 'All emergency exits are clearly marked and unobstructed' },
    ],
  },
  {
    id: 'violence',
    label: 'Workplace Violence Prevention',
    questions: [
      { id: 'v1', text: 'Written workplace violence prevention policy exists and is communicated to staff' },
      { id: 'v2', text: 'Employees have received workplace violence prevention training in the past year' },
      { id: 'v3', text: 'Clear, accessible process exists for reporting threats or suspicious behavior' },
      { id: 'v4', text: 'Panic button or emergency notification system is available and tested regularly' },
    ],
  },
  {
    id: 'environment',
    label: 'Environmental Safety',
    questions: [
      { id: 'n1', text: 'Floors and walkways are free of hazards (spills, cables, clutter)' },
      { id: 'n2', text: 'Equipment safety guards are in place and functioning' },
      { id: 'n3', text: 'Hazardous materials are properly stored, labeled, and inventoried' },
      { id: 'n4', text: 'Adequate PPE is available and accessible for all required tasks' },
    ],
  },
  {
    id: 'culture',
    label: 'Security Culture',
    questions: [
      { id: 'c1', text: 'Employees feel comfortable reporting safety concerns without fear of retaliation' },
      { id: 'c2', text: 'Near-miss incidents are consistently reported, reviewed, and documented' },
      { id: 'c3', text: 'Regular security walkthroughs or inspections are conducted' },
      { id: 'c4', text: 'Previous security incidents have been reviewed and corrective actions implemented' },
    ],
  },
]

export const ALL_QUESTIONS = SURVEY_CATEGORIES.flatMap((c) => c.questions)
export const TOTAL_QUESTIONS = ALL_QUESTIONS.length
