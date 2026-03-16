import type { BadgeVariant } from '../components/ui'

// ─── Types ────────────────────────────────────────────────────────────────────

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
}

export type AssignableUser = { id: string; name: string; email: string }
export type AdminCompany = { id: string; company_name: string }

export type MonteCarloResult = {
  expected_loss?: number
  p50?: number
  p90?: number
  p95?: number
  by_category?: Array<{ category: string; expected_loss: number; p50: number; p95: number }>
}

export type CohortResult = {
  cohort: string
  score: number
  employee_count?: number
}

export type BenchmarkResult = {
  naics_code?: string
  industry_name?: string
  dimensions?: Array<{
    dimension: string
    company_score: number
    industry_median: number
    percentile_rank: number
  }>
}

export type AnomalyResult = {
  anomalies?: Array<{
    metric: string
    detected_at: string
    value: number
    expected_low: number
    expected_high: number
    sigma: number
  }>
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

export const DIMENSION_LABELS: Record<string, string> = {
  compliance: 'Compliance',
  incidents: 'Incidents',
  er_cases: 'ER Cases',
  workforce: 'Workforce',
  legislative: 'Legislative',
}

export const DIMENSION_COLORS: Record<string, string> = {
  compliance: '#6366f1',
  incidents: '#f59e0b',
  er_cases: '#ef4444',
  workforce: '#10b981',
  legislative: '#8b5cf6',
}

export function fmt(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString()
}

export function fmtMoney(n: number | null | undefined): string {
  if (n == null) return '—'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n)
}

export function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}
