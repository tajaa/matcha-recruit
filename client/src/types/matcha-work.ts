export type MWTaskType =
  | 'chat'
  | 'offer_letter'
  | 'review'
  | 'workbook'
  | 'onboarding'
  | 'presentation'
  | 'handbook'
  | 'policy'

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

export interface MWMessageMetadata {
  compliance_reasoning?: ComplianceReasoningLocation[]
  ai_reasoning_steps?: AIReasoningStep[]
  referenced_categories?: string[]
  referenced_locations?: string[]
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
