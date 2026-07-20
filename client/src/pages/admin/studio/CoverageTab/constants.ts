import type { LaborScopeResponse } from './types'


// Research model tier (ported from the retired Specialization Research page).
export const MODEL_LABELS: Record<string, { label: string; model: string; color: string }> = {
  light: { label: 'Light', model: 'Gemini 3 Flash', color: 'bg-blue-900/50 text-blue-300' },
  heavy: { label: 'Pro', model: 'Gemini 3.1 Pro', color: 'bg-purple-900/50 text-purple-300' },
}

// Canonical industry slugs — what the matrix and /scope-registry/resolve expect.
export const INDUSTRIES = [
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'biotech', label: 'Biotech / Life Sciences' },
  { value: 'hospitality', label: 'Restaurant / Hospitality' },
  { value: 'retail', label: 'Retail' },
  { value: 'technology', label: 'Tech / Professional Services' },
  { value: 'fast food', label: 'Fast Food' },
  { value: 'manufacturing', label: 'Construction / Manufacturing' },
  { value: 'warehousing', label: 'Warehousing & Storage' },
]

export const HEADCOUNTS = ['', '1-10', '11-50', '51-100', '101-500', '501-1000', '1001+']

// Rough midpoint headcount so conditional strata (FMLA ≥ 50) evaluate in the
// resolve preview. The registry keys on employee_count.
export const HEADCOUNT_MIDPOINT: Record<string, number> = {
  '1-10': 5, '11-50': 30, '51-100': 75, '101-500': 300, '501-1000': 750, '1001+': 1500,
}

export const GROUP_ORDER = [
  'Core Labor', 'Supplementary', 'Healthcare', 'Oncology',
  'Medical Compliance', 'Life Sciences', 'Manufacturing',
]

// Ledger pipeline-status → dot color for the cross-jurisdiction industry grid.
export const GRID_STATUS: Record<string, string> = {
  covered: 'bg-emerald-500',
  empty: 'bg-zinc-600',
  in_progress: 'bg-blue-400 animate-pulse',
  pending: 'bg-amber-400',
  failed: 'bg-red-500',
  absent: 'bg-zinc-800 border border-zinc-700',
}

export const SOURCE_BADGE: Record<string, string> = {
  base: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  triggered: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  specialty: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
  focused: 'bg-zinc-500/15 text-zinc-300 border-zinc-500/30',
}

// Obligation severity (RKD) — 'critical' | 'high' | 'moderate' | 'low'. Only the
// two urgent bands render a badge; moderate/low stay quiet to avoid noise.
export const SEVERITY_BADGE: Record<string, string> = {
  critical: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  high: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
}

export const LEVEL_LABELS: [keyof LaborScopeResponse['registry']['levels'], string][] = [
  ['federal', 'Federal'], ['state', 'State'], ['city', 'City / Local'],
]
