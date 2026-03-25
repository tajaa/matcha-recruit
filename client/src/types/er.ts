// ER Copilot shared types — mirrors server/app/matcha/models/er_case.py

export type ERCaseStatus = 'open' | 'in_review' | 'pending_determination' | 'closed'
export type ERCaseCategory = 'harassment' | 'discrimination' | 'safety' | 'retaliation' | 'policy_violation' | 'misconduct' | 'wage_hour' | 'other'
export type ERCaseOutcome = 'termination' | 'disciplinary_action' | 'retraining' | 'no_action' | 'resignation' | 'other'
export type ERDocumentType = 'transcript' | 'policy' | 'email' | 'other'
export type ERProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed'
export type ERNoteType = 'general' | 'question' | 'answer' | 'guidance' | 'system'
export type GuidancePriority = 'high' | 'medium' | 'low'
export type GuidanceActionType = 'run_analysis' | 'open_tab' | 'search_evidence' | 'upload_document'

export type ERCase = {
  id: string
  case_number: string
  title: string
  description: string | null
  status: ERCaseStatus
  category: ERCaseCategory | null
  outcome: ERCaseOutcome | null
  company_id: string | null
  created_by: string | null
  assigned_to: string | null
  document_count: number
  involved_employees: { employee_id: string; role: string }[]
  created_at: string
  updated_at: string
  closed_at: string | null
}

export type ERNote = {
  id: string
  case_id: string
  note_type: ERNoteType
  content: string
  metadata: Record<string, unknown> | null
  created_by: string | null
  created_at: string
}

export type ERDocument = {
  id: string
  case_id: string
  document_type: ERDocumentType
  filename: string
  mime_type: string | null
  file_size: number | null
  pii_scrubbed: boolean
  processing_status: ERProcessingStatus
  processing_error: string | null
  parsed_at: string | null
  uploaded_by: string | null
  created_at: string
}

export type ERDocumentUploadResponse = {
  document: ERDocument
  task_id: string | null
  message: string
}

export type SuggestedGuidanceAction = {
  type: GuidanceActionType
  label: string
  tab?: string | null
  analysis_type?: string | null
  search_query?: string | null
}

export type SuggestedGuidanceCard = {
  id: string
  title: string
  recommendation: string
  rationale: string
  priority: GuidancePriority
  blockers: string[]
  action: SuggestedGuidanceAction
}

export type SuggestedGuidanceResponse = {
  summary: string
  cards: SuggestedGuidanceCard[]
  generated_at: string
  model: string
  fallback_used: boolean
  determination_suggested: boolean
  determination_confidence: number
  determination_signals: string[]
}

export type CaseListResponse = {
  cases: ERCase[]
  total: number
}

export type TimelineEvent = {
  date: string
  time: string | null
  description: string
  participants: string[]
  source_document_id: string
  source_location: string
  confidence: 'high' | 'medium' | 'low'
  evidence_quote: string
}

export type TimelineAnalysisResponse = {
  analysis: {
    events: TimelineEvent[]
    gaps_identified: string[]
    timeline_summary: string
  }
  source_documents: string[]
  generated_at: string | null
}

// Discrepancies
export interface DiscrepancyItem {
  subject: string
  statement_a: string
  statement_b: string
  severity: 'high' | 'medium' | 'low'
  source_a: string
  source_b: string
  notes?: string
}
export interface CredibilityNote { witness: string; note: string; factors: string[] }
export interface DiscrepancyAnalysis { discrepancies: DiscrepancyItem[]; credibility_notes: CredibilityNote[]; summary: string }
export interface DiscrepancyAnalysisResponse { analysis: DiscrepancyAnalysis; source_documents: string[]; generated_at: string | null }

// Similar Cases
export interface SimilarCaseMatch {
  case_id: string; case_number: string; title: string
  category: ERCaseCategory | null; outcome: ERCaseOutcome | null; status: ERCaseStatus
  created_at: string; closed_at: string | null; resolution_days: number | null
  outcome_effective: boolean | null; similarity_score: number
  score_breakdown: { category_match: number; outcome_relevance: number; status_maturity: number; evidence_profile: number; temporal_recency: number; intake_context_overlap: number; text_similarity: number; investigation_pattern_similarity: number }
  common_factors: string[]; relevance_note: string | null
}
export interface SimilarCasesAnalysis { matches: SimilarCaseMatch[]; pattern_summary: string | null; outcome_distribution: Record<string, number>; generated_at: string; from_cache: boolean; cache_reason: string | null }

// Evidence Search
export interface EvidenceSearchResult { chunk_id: string; content: string; speaker: string | null; source_file: string; document_type: ERDocumentType; page_number: number | null; line_range: string | null; similarity: number; metadata: Record<string, unknown> | null }
export interface EvidenceSearchResponse { results: EvidenceSearchResult[]; query: string; total_chunks: number }

// Outcome Analysis
export interface OutcomeOption { determination: 'substantiated' | 'unsubstantiated' | 'inconclusive'; recommended_action: ERCaseOutcome; action_label: string; reasoning: string; policy_basis: string; hr_considerations: string; precedent_note: string; confidence: 'high' | 'medium' | 'low'; applies_to?: string }
export interface OutcomeAnalysisResponse { outcomes: OutcomeOption[]; case_summary: string; generated_at: string; model: string }

// Export
export interface ShareLink { id: string; token: string; created_at: string; expires_at: string | null; revoked_at: string | null; download_count: number; last_downloaded_at: string | null; filename: string }

// Helpers

export const CATEGORIES: ERCaseCategory[] = [
  'harassment', 'discrimination', 'safety', 'retaliation',
  'policy_violation', 'misconduct', 'wage_hour', 'other',
]

export const categoryLabel: Record<string, string> = {
  harassment: 'Harassment',
  discrimination: 'Discrimination',
  safety: 'Safety',
  retaliation: 'Retaliation',
  policy_violation: 'Policy Violation',
  misconduct: 'Misconduct',
  wage_hour: 'Wage & Hour',
  other: 'Other',
}

export const statusLabel: Record<string, string> = {
  open: 'Open',
  in_review: 'In Review',
  pending_determination: 'Pending',
  closed: 'Closed',
}

export const outcomeLabel: Record<string, string> = {
  termination: 'Termination',
  disciplinary_action: 'Disciplinary Action',
  retraining: 'Retraining',
  no_action: 'No Action',
  resignation: 'Resignation',
  other: 'Other',
}

export const documentTypeLabel: Record<string, string> = {
  transcript: 'Transcript',
  policy: 'Policy',
  email: 'Email',
  other: 'Other',
}

export const NOTE_TYPES: { value: ERNoteType; label: string }[] = [
  { value: 'general', label: 'General' },
  { value: 'question', label: 'Question' },
  { value: 'answer', label: 'Answer' },
  { value: 'guidance', label: 'Guidance' },
  { value: 'system', label: 'System' },
]
