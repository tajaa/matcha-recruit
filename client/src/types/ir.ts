// IR Incident shared types — mirrors server/app/matcha/models/ir_incident.py
import type { BadgeVariant } from '../components/ui'

// ── Enums ──

export type IRIncidentType = 'safety' | 'behavioral' | 'property' | 'near_miss' | 'other'
export type IRSeverity = 'low' | 'medium' | 'high' | 'critical'
export type IRStatus = 'reported' | 'investigating' | 'action_required' | 'resolved' | 'closed'
export type IRDocumentType = 'photo' | 'form' | 'statement' | 'other'

// ── Core models ──

export type IRWitness = {
  name: string
  contact?: string | null
  statement?: string | null
}

export type IRIncident = {
  id: string
  incident_number: string
  title: string
  description: string | null
  incident_type: IRIncidentType
  severity: IRSeverity
  status: IRStatus
  occurred_at: string | null
  location: string | null
  reported_by_name: string
  reported_by_email: string | null
  reported_at: string
  is_anonymous: boolean
  witnesses: IRWitness[]
  category_data: Record<string, unknown>
  root_cause: string | null
  corrective_actions: string | null
  involved_employee_ids: string[]
  er_case_id: string | null
  document_count: number
  company_id: string | null
  location_id: string | null
  created_at: string
  updated_at: string
}

export type IRIncidentCreate = {
  title: string
  description?: string | null
  incident_type: IRIncidentType
  severity?: IRSeverity
  occurred_at: string
  location?: string | null
  reported_by_name: string
  reported_by_email?: string | null
  witnesses?: IRWitness[]
  category_data?: Record<string, unknown> | null
}

export type IRDocument = {
  id: string
  incident_id: string
  document_type: string
  filename: string
  file_size: number | null
  created_at: string
}

// ── Analysis types ──

export type IRCategorizationAnalysis = {
  suggested_type: IRIncidentType
  confidence: number
  reasoning: string
  generated_at: string
  from_cache?: boolean
}

export type IRSeverityAnalysis = {
  suggested_severity: IRSeverity
  factors: string[]
  reasoning: string
  generated_at: string
  from_cache?: boolean
}

export type IRRootCauseAnalysis = {
  primary_cause: string
  contributing_factors: string[]
  prevention_suggestions: string[]
  reasoning: string
  generated_at: string
  from_cache?: boolean
}

export type IRRecommendationItem = {
  action: string
  priority: 'immediate' | 'short_term' | 'long_term'
  responsible_party?: string | null
  estimated_effort?: string | null
}

export type IRRecommendationsAnalysis = {
  recommendations: IRRecommendationItem[]
  summary: string
  generated_at: string
  from_cache?: boolean
}

// ── Precedent / Similar analysis ──

export type IRScoreBreakdown = {
  type_match: number
  severity_proximity: number
  category_overlap: number
  location_similarity: number
  temporal_pattern: number
  text_similarity: number
  root_cause_similarity: number
}

export type IRPrecedentMatch = {
  incident_id: string
  incident_number: string
  title: string
  incident_type: IRIncidentType
  severity: IRSeverity
  status: IRStatus
  occurred_at: string
  resolved_at?: string | null
  resolution_days?: number | null
  root_cause?: string | null
  corrective_actions?: string | null
  resolution_effective?: boolean | null
  similarity_score: number
  score_breakdown: IRScoreBreakdown
  common_factors: string[]
}

export type IRPrecedentAnalysis = {
  precedents: IRPrecedentMatch[]
  pattern_summary?: string | null
  generated_at: string
  from_cache?: boolean
}

// ── Policy mapping ──

export type IRPolicyMatch = {
  policy_id: string
  policy_title: string
  relevance: 'violated' | 'bent' | 'related'
  confidence: number
  reasoning: string
  relevant_excerpt?: string | null
}

export type IRPolicyMappingAnalysis = {
  matches: IRPolicyMatch[]
  summary: string
  no_matching_policies?: boolean
  generated_at: string
  from_cache?: boolean
}

// ── Consistency guidance ──

export type IRActionProbability = {
  category: string
  probability: number
  weighted_count: number
}

export type IRConsistencyGuidance = {
  sample_size: number
  effective_sample_size: number
  confidence: 'insufficient' | 'limited' | 'strong'
  unprecedented: boolean
  action_distribution?: IRActionProbability[] | null
  dominant_action?: string | null
  dominant_probability?: number | null
  weighted_avg_resolution_days?: number | null
  weighted_effectiveness_rate?: number | null
  consistency_insight?: string | null
  generated_at: string
  from_cache?: boolean
}

// ── Consistency analytics (company-wide) ──

export type IRActionByType = {
  incident_type: string
  total: number
  actions: IRActionProbability[]
}

export type IRActionBySeverity = {
  severity: string
  total: number
  actions: IRActionProbability[]
}

export type IRConsistencyAnalytics = {
  total_resolved: number
  total_with_actions: number
  action_distribution: IRActionProbability[]
  by_incident_type: IRActionByType[]
  by_severity: IRActionBySeverity[]
  avg_resolution_by_action: Record<string, number>
  generated_at: string
  from_cache?: boolean
}

// ── Analytics ──

export type IRAnalyticsSummary = {
  total: number
  open: number
  investigating: number
  resolved: number
  closed: number
  critical: number
  high: number
  medium: number
  low: number
  by_type: Record<string, number>
}

export type IRTrendPoint = { date: string; count: number }
export type IRTrendsData = { interval: string; data: IRTrendPoint[] }
export type IRLocationData = { location: string; count: number; severity_breakdown: Record<string, number> }

// ── Investigation interviews ──

export type InvestigationInterview = {
  id: string
  incident_id: string
  interview_id: string
  er_case_id?: string | null
  interviewee_role?: string | null
  interviewee_name?: string | null
  interviewee_email?: string | null
  status: string
  has_transcript?: boolean
  invite_token?: string | null
  invite_sent_at?: string | null
  created_at: string
  completed_at?: string | null
}

export type InvestigationInterviewCreate = {
  interviewee_name: string
  interviewee_email?: string | null
  interviewee_role: string
  send_invite?: boolean
  custom_message?: string | null
}

// ── Label helpers ──

export function typeLabel(t: string): string {
  return t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function statusLabel(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function severityLabel(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

// ── Badge variant maps ──

export const SEVERITY_BADGE: Record<string, BadgeVariant> = {
  critical: 'danger', high: 'danger', medium: 'warning', low: 'neutral',
}

export const STATUS_BADGE: Record<string, BadgeVariant> = {
  reported: 'neutral', investigating: 'warning', action_required: 'danger', resolved: 'success', closed: 'neutral',
}

export const RELEVANCE_BADGE: Record<string, BadgeVariant> = {
  violated: 'danger', bent: 'warning', related: 'neutral',
}

// ── IR Type → ER Category mapping ──

export const IR_TYPE_TO_ER_CATEGORY: Record<string, string> = {
  safety: 'safety',
  behavioral: 'misconduct',
  harassment: 'harassment',
  discrimination: 'discrimination',
  property: 'other',
  near_miss: 'safety',
  theft: 'misconduct',
  policy_violation: 'policy_violation',
  other: 'other',
}
