import type { BadgeVariant } from '../components/ui'

// ─── Types ────────────────────────────────────────────────────────────────────

export type Band = 'low' | 'moderate' | 'high' | 'critical'

export type DimensionResult = {
  score: number
  band: string
  factors: string[]
  raw_data: Record<string, unknown>
}

export type Recommendation = {
  dimension: string
  priority: string
  title: string
  guidance: string
}

export type RiskAssessment = {
  overall_score: number
  overall_band: string
  dimensions: Record<string, DimensionResult>
  computed_at: string
  weights: Record<string, number>
  report?: string
  recommendations?: Recommendation[]
}

export type HistoryEntry = {
  overall_score: number
  overall_band: string
  dimensions: Record<string, number>
  computed_at: string
  source?: string
}

export type ActionItem = {
  id: string
  title: string
  description?: string
  source_type: string
  source_ref?: string
  assigned_to?: string
  assigned_to_name?: string
  due_date?: string
  status: string
  created_at: string
  closed_at?: string
}

export type AssignableUser = { id: string; name: string; email: string }
export type AdminCompany = { id: string; company_name: string }

// ─── Cost of Risk ────────────────────────────────────────────────────────────

export type CostLineItem = {
  key: string
  label: string
  basis: string
  affected_count: number
  low: number
  high: number
  formula?: string
  statute?: string
  risk_context?: string
  benchmark?: string
}

export type CostOfRisk = {
  line_items: CostLineItem[]
  total_low: number
  total_high: number
}

// ─── Monte Carlo ─────────────────────────────────────────────────────────────

export type MonteCarloCategoryResult = {
  key: string
  label: string
  frequency_type: string
  frequency_lambda: number
  expected_loss: number
  percentiles: { p10: number; p25: number; p50: number; p75: number; p90: number; p95: number; p99: number }
  zero_loss_pct: number
}

export type MonteCarloAggregateResult = {
  expected_annual_loss: number
  percentiles: { p5: number; p10: number; p25: number; p50: number; p75: number; p90: number; p95: number; p99: number }
  var_95: number
  var_99: number
  cvar_95: number
  max_simulated: number
}

export type MonteCarloResult = {
  iterations: number
  categories: Record<string, MonteCarloCategoryResult>
  aggregate: MonteCarloAggregateResult
  computed_at: string
}

// ─── Cohort Analysis ─────────────────────────────────────────────────────────

export type CohortResult = {
  label: string
  headcount: number
  headcount_pct: number
  incident_count: number
  incident_rate: number
  er_case_count: number
  discipline_count: number
  risk_concentration: number
  flags: string[]
}

// ─── Industry Benchmarks ─────────────────────────────────────────────────────

export type BenchmarkMetric = {
  metric: string
  company_value: number
  industry_median: number
  ratio: number
  percentile: number
  interpretation?: string
}

export type BenchmarkResult = {
  naics_code: string
  naics_label: string
  metrics: BenchmarkMetric[]
}

// ─── Anomaly Detection ───────────────────────────────────────────────────────

export type AnomalyItem = {
  metric: string
  period: string
  value: number
  rolling_mean: number
  rolling_std: number
  z_score: number
  severity: 'warning' | 'alert'
  description: string
}

export type MetricTimeSeries = {
  metric: string
  label: string
  data_points: number
  anomalies: AnomalyItem[]
}

export type AnomalyDetectionResult = {
  has_sufficient_data: boolean
  data_points_available: number
  metrics: MetricTimeSeries[]
  total_anomalies: number
  alert_count: number
  warning_count: number
}

// ─── Employee Compliance ─────────────────────────────────────────────────────

export type EmployeeViolation = {
  employee_name: string
  pay_rate: number
  threshold: number
  shortfall: number
  pay_classification: string
  location_city: string | null
  location_state: string | null
}

export type OpenCase = {
  case_id: string
  title: string
  status: string
  category: string | null
  created_at: string | null
}

// ─── Pre-Termination Analytics ───────────────────────────────────────────────

export type PreTermAnalytics = {
  total_checks: number
  by_band: Record<string, number>
  avg_score: number
  override_rate: number
  most_common_red_flags: Array<{ dimension: string; count: number }>
  by_outcome: Record<string, number>
  period: string
}

// ─── ER Case Metrics ─────────────────────────────────────────────────────────

export type ERCaseMetrics = {
  period_days: number
  total_cases: number
  by_status: Record<string, number>
  by_category: Record<string, number>
  by_outcome: Record<string, number>
}

// ─── Constants ───────────────────────────────────────────────────────────────

export const BAND_COLOR: Record<Band, { text: string; dot: string; badge: string; bar: string }> = {
  low:      { text: 'text-emerald-400', dot: 'bg-emerald-500',           badge: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20', bar: 'bg-emerald-500' },
  moderate: { text: 'text-amber-400',   dot: 'bg-amber-500',             badge: 'bg-amber-500/10 text-amber-400 border border-amber-500/20',       bar: 'bg-amber-500'   },
  high:     { text: 'text-orange-400',  dot: 'bg-orange-500',            badge: 'bg-orange-500/10 text-orange-400 border border-orange-500/20',     bar: 'bg-orange-500'  },
  critical: { text: 'text-red-400',     dot: 'bg-red-500 animate-pulse', badge: 'bg-red-500/10 text-red-400 border border-red-500/20',              bar: 'bg-red-500'     },
}

export const BAND_LABEL: Record<Band, string> = {
  low: 'Low', moderate: 'Moderate', high: 'High', critical: 'Critical',
}

export const BAND_BADGE: Record<string, BadgeVariant> = {
  low: 'success',
  moderate: 'warning',
  high: 'warning',
  critical: 'danger',
}

export const PRIORITY_BADGE: Record<string, BadgeVariant> = {
  high: 'danger',
  medium: 'warning',
  low: 'neutral',
}

export const PRIORITY_COLOR: Record<string, { badge: string }> = {
  critical: { badge: 'bg-red-500/10 text-red-400 border border-red-500/20' },
  high:     { badge: 'bg-orange-500/10 text-orange-400 border border-orange-500/20' },
  medium:   { badge: 'bg-amber-500/10 text-amber-400 border border-amber-500/20' },
  low:      { badge: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' },
}

export const DIMENSION_LABELS: Record<string, string> = {
  compliance: 'Compliance',
  incidents: 'Incidents',
  er_cases: 'ER Cases',
  workforce: 'Workforce',
  legislative: 'Legislative',
}

export const DIMENSION_COLORS: Record<string, string> = {
  compliance: '#f59e0b',
  incidents: '#ef4444',
  er_cases: '#3b82f6',
  workforce: '#a855f7',
  legislative: '#06b6d4',
}

export const DIMENSION_ORDER = ['compliance', 'incidents', 'er_cases', 'workforce', 'legislative'] as const

export const DIMENSION_HELP: Record<string, string> = {
  overall: 'The weighted composite of all five dimension scores. Higher means more exposure. Weights: Compliance 30%, Incidents 25%, ER Cases 25%, Workforce 15%, Legislative 5%.',
  compliance: 'Measures regulatory compliance gaps across your locations — minimum wage violations, missing postings, and jurisdiction-specific requirements. Contributes 30% of the overall score.',
  incidents: 'Tracks workplace safety and behavioral incident frequency, severity, and resolution time. Contributes 25% of the overall score.',
  er_cases: 'Evaluates open employee relations cases, escalation patterns, and unresolved disputes. Contributes 25% of the overall score.',
  workforce: 'Assesses workforce-level risks like turnover concentration, onboarding gaps, and headcount exposure. Contributes 15% of the overall score.',
  legislative: 'Monitors upcoming legislation and regulatory changes that could impact your operations. Contributes 5% of the overall score.',
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

export function decodeTokenRole(): string | null {
  const token = localStorage.getItem('matcha_access_token')
  if (!token) return null
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.role ?? null
  } catch {
    return null
  }
}

export function fmt(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString()
}

export function fmtMoney(n: number | null | undefined): string {
  if (n == null) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}

export function formatCurrency(value: number): string {
  return value.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
}

export function fmtCompact(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  return `$${Math.round(n / 1000)}K`
}

export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function getBandForScore(score: number): Band {
  if (score <= 25) return 'low'
  if (score <= 50) return 'moderate'
  if (score <= 75) return 'high'
  return 'critical'
}
