export type MWTaskType =
  | 'chat'
  | 'offer_letter'
  | 'review'
  | 'workbook'
  | 'onboarding'
  | 'presentation'
  | 'handbook'
  | 'policy'
  | 'resume_batch'
  | 'inventory'
  | 'project'

export interface ResumeCandidate {
  id: string
  filename: string
  resume_url: string | null
  name: string | null
  email: string | null
  phone: string | null
  location: string | null
  current_title: string | null
  experience_years: number | null
  skills: string[] | null
  education: string | null
  certifications: string[] | null
  summary: string | null
  strengths: string[] | null
  flags: string[] | null
  status: string
  interview_id?: string | null
  interview_status?: string | null
  interview_score?: number | null
  interview_summary?: string | null
}

export interface RecruitingPosting {
  title?: string
  description?: string
  requirements?: string
  compensation?: string
  location?: string
  employment_type?: string
}

export interface RecruitingData {
  posting?: RecruitingPosting
  candidates?: ResumeCandidate[]
  shortlist_ids?: string[]
}

export interface MWProject {
  id: string
  title: string
  project_type: 'general' | 'presentation' | 'recruiting'
  sections: ProjectSection[]
  project_data: RecruitingData | Record<string, unknown>
  status: string
  is_pinned: boolean
  version: number
  chat_count: number
  chats?: MWThread[]
  created_at: string
  updated_at: string
}

export interface AgentEmail {
  id: string
  subject: string
  from: string
  date: string
  body: string
}

export interface ProjectSection {
  id: string
  title: string | null
  content: string
  source_message_id: string | null
}

export interface InventoryItem {
  id: string
  filename: string
  product_name: string | null
  sku: string | null
  category: string | null
  quantity: number | null
  unit: string | null
  unit_cost: number | null
  total_cost: number | null
  vendor: string | null
  par_level: number | null
  status: string
}

export interface PresentationSlide {
  title: string
  bullets: string[] | null
  speaker_notes: string | null
}

export interface PresentationState {
  presentation_title: string | null
  subtitle: string | null
  theme: string | null
  slides: PresentationSlide[] | null
  cover_image_url: string | null
  generated_at: string | null
}

export interface MWThread {
  id: string
  title: string
  status: string
  task_type: MWTaskType | null
  is_pinned: boolean
  node_mode: boolean
  compliance_mode: boolean
  payer_mode: boolean
  version: number
  created_at: string
  updated_at: string
}

// Gemini's reasoning step
export interface AIReasoningStep {
  step: number
  question: string
  answer: string
  conclusion: string
  sources: string[]
}

// Pre-computed jurisdiction level
export interface ComplianceReasoningLevel {
  jurisdiction_level: string
  jurisdiction_name: string
  title: string
  current_value: string | null
  numeric_value: number | null
  source_url: string | null
  statute_citation: string | null
  trigger_condition: Record<string, unknown> | null
  is_governing: boolean
  effective_date: string | null
  last_verified_at: string | null
  previous_value: string | null
  last_changed_at: string | null
  expiration_date: string | null
  requires_written_policy: boolean
  penalty_summary: string | null
  enforcing_agency: string | null
}

export interface ComplianceReasoningCategory {
  category: string
  governing_level: string
  precedence_type: 'floor' | 'ceiling' | 'supersede' | 'additive' | null
  reasoning_text: string | null
  legal_citation: string | null
  all_levels: ComplianceReasoningLevel[]
}

export interface ComplianceReasoningLocation {
  location_id: string
  location_label: string
  facility_attributes: Record<string, unknown> | null
  activated_profiles: { label: string; categories: string[] }[]
  categories: ComplianceReasoningCategory[]
}

export interface PayerPolicySource {
  payer_name: string
  policy_title: string | null
  policy_number: string | null
  source_url: string | null
  similarity: number
}

export interface AffectedEmployeeGroup {
  location: string
  count: number
  match_type: 'exact' | 'state'
}

export interface ComplianceGap {
  category: string
  label: string
  status: 'missing' | 'partial'
}

export interface MWMessageMetadata {
  compliance_reasoning?: ComplianceReasoningLocation[]
  ai_reasoning_steps?: AIReasoningStep[]
  referenced_categories?: string[]
  referenced_locations?: string[]
  payer_sources?: PayerPolicySource[]
  affected_employees?: AffectedEmployeeGroup[]
  compliance_gaps?: ComplianceGap[]
}

export interface MWMessage {
  id: string
  thread_id: string
  role: 'user' | 'assistant'
  content: string
  version_created: number | null
  metadata: MWMessageMetadata | null
  created_at: string
}

export interface MWThreadDetail extends MWThread {
  current_state: Record<string, unknown>
  linked_offer_letter_id: string | null
  messages: MWMessage[]
}

export interface MWTokenUsage {
  prompt_tokens: number | null
  completion_tokens: number | null
  total_tokens: number | null
  estimated: boolean
  model: string | null
  cost_dollars: number | null
}

export interface MWSendResponse {
  user_message: MWMessage
  assistant_message: MWMessage
  current_state: Record<string, unknown>
  version: number
  task_type: MWTaskType | null
  pdf_url: string | null
  token_usage: MWTokenUsage | null
}

export interface MWCreateResponse {
  id: string
  title: string
  status: string
  current_state: Record<string, unknown>
  version: number
  task_type: MWTaskType | null
  is_pinned: boolean
  node_mode: boolean
  compliance_mode: boolean
  payer_mode: boolean
  created_at: string
  assistant_reply: string | null
  pdf_url: string | null
}

// SSE event types from the stream endpoint
export type MWStreamEvent =
  | { type: 'usage'; data: MWTokenUsage & { stage: 'estimate' | 'final' } }
  | { type: 'status'; message: string }
  | { type: 'complete'; data: MWSendResponse }
  | { type: 'error'; message: string }
