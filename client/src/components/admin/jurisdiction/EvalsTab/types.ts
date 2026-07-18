// ── Types ─────────────────────────────────────────────────────────────────────

export type Subscores = {
  completeness: number | null
  accuracy: number | null
  authority: number | null
  freshness: number | null
  tagging: number | null
}

export type ScorecardCell = {
  jurisdiction_id: string
  jurisdiction_label: string | null
  industry: string | null
  composite: number | null
  onboarding_ready: boolean | null
  status: string | null
  subscores: Partial<Subscores>
  blocking: string[]
  measured_at: string | null
}

export type EvalRun = {
  id: string
  suites: string[]
  status: string
  trigger_source: string
  totals: Record<string, unknown> | null
  error_text: string | null
  started_at: string | null
  finished_at: string | null
}

export type Finding = {
  id: string
  suite: string
  finding_type: string
  severity: 'critical' | 'warn' | 'info'
  jurisdiction_label: string | null
  requirement_key: string | null
  category: string | null
  industry: string | null
  expected: Record<string, unknown> | null
  observed: Record<string, unknown> | null
  status: string
  created_at: string | null
}

export type RunDetail = {
  run: EvalRun
  finding_counts: { finding_type: string; severity: string; count: number }[]
  total: number
  findings: Finding[]
}

export type CoreChecklist = {
  score: number
  present: number
  total: number
  complete: boolean
  items: { category: string; key: string; present: boolean }[]
}

export type Readiness = {
  found: boolean
  status: string
  ready?: boolean
  industry: string
  depth?: 'core' | 'full'
  composite: number | null
  subscores: Partial<Subscores>
  blocking: string[]
  missing_keys: Record<string, string[]>
  golden_fact_count: number
  open_critical_findings: number
  core_checklist: CoreChecklist | null
}

export type GoldenFact = {
  jurisdiction: string
  requirement_key: string
  category: string
  comparator: string
  severity: string
  effective_from: string
  effective_to: string | null
  authority_url: string
  curated_by: string
  verified_by: string | null
  notes: string | null
  state: 'active' | 'pending' | 'expired'
}

export type GoldenResponse = { facts: GoldenFact[]; total: number; active: number; unverified: number }

export type BaselineItem = {
  category: string
  key: string
  citation: string
  authority_url: string
  applies_note: string
  present: boolean
}
export type BaselineJurisdiction = {
  label: string
  jurisdiction_found: boolean
  expected: number
  present: number
  score: number | null
  items: BaselineItem[]
}

export type View = 'scorecard' | 'runs' | 'golden' | 'baseline'
