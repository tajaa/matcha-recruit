import type { Decision, DecisionState, Palette } from './types'

export const DECISIONS: Decision[] = [
  {
    id: 'plan',
    label: 'Written WVP Plan',
    weighing: ['Matching statute', 'Screening record', 'Scoring gap'],
    question: 'Plan exists, site-specific, employee-accessible?',
    result: 'GAP',
    remediation: 'Written plan drafted',
    cite: 'CA Lab §6401.9',
    status: 'Checking: Written Plan',
  },
  {
    id: 'training',
    label: 'Annual Training',
    weighing: ['Matching statute', 'Screening record', 'Scoring gap'],
    question: 'All employees trained interactively < 12 months?',
    result: 'GAP',
    remediation: 'Training program scoped',
    cite: 'CA Lab §6401.9',
    status: 'Checking: Annual Training',
  },
  {
    id: 'log',
    label: 'Violent Incident Log',
    weighing: ['Matching statute', 'Screening record', 'Scoring gap'],
    question: 'Log incidents + threats + near-misses, retain 5y?',
    result: 'GAP',
    remediation: 'Incident log deployed',
    cite: 'CA Lab §6401.9',
    status: 'Checking: Incident Log',
  },
  {
    id: 'hazard',
    label: 'Hazard Assessment',
    weighing: ['Matching statute', 'Screening record', 'Scoring gap'],
    question: 'Per-site assessment with workplace-specific hazards?',
    result: 'GAP',
    remediation: 'Site assessments scheduled',
    cite: 'CA Lab §6401.9',
    status: 'Checking: Hazard Assessment',
  },
  {
    id: 'review',
    label: 'Annual Review',
    weighing: ['Matching statute', 'Screening record', 'Scoring gap'],
    question: 'Annual review + post-incident review cadence in place?',
    result: 'GAP',
    remediation: 'Review cadence set',
    cite: 'CA Lab §6401.9',
    status: 'Checking: Annual Review',
  },
]

export const SCENARIO = {
  bill: 'SB 553',
  effective: 'Effective Jul 1, 2024',
  facts: 'SF coffee chain · 8 locations · 87 employees · last audit: never',
  exposure: 'Six-figure',
  exposureSubtext: 'Cal/OSHA serious violation × 8 locations',
}

export const SYNTHESIS = {
  laborHours: 'Low',
  timeline: 'Weeks',
  cost: 'Modest',
  exposureAvoided: 'Six-figure',
}

const EMERALD = '#34d399'
const RED = '#f87171'
const AMBER = '#d7ba7d'
export const ZINC_LINE = 'rgba(255,255,255,0.08)'

// The default (gold) palette keeps the semantic red/green/amber for the
// original /platform page. The mono palette collapses everything to one amber
// accent + neutral grays for the simpler-pages design system — amber marks
// what needs attention (the audit, its gaps, exposure), everything resolved
// or structural stays neutral, so the card reads as one system, not a
// stoplight.
export const GOLD: Palette = { red: RED, emerald: EMERALD, amber: AMBER, live: EMERALD, neutral: '#cbd5e1' }
export const MONO: Palette = { red: '#F59E0B', emerald: '#8b8f96', amber: '#F59E0B', live: '#F59E0B', neutral: '#cbd5e1' }

export const INITIAL_STATES: DecisionState[] = DECISIONS.map(() => ({ phase: 'pending', weighIdx: 0 }))
