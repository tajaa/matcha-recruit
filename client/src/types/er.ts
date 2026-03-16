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
]
