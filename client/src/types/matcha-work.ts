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
  version: number
  created_at: string
  updated_at: string
}

export interface MWMessage {
  id: string
  thread_id: string
  role: 'user' | 'assistant'
  content: string
  version_created: number | null
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
  created_at: string
  assistant_reply: string | null
  pdf_url: string | null
}

// SSE event types from the stream endpoint
export type MWStreamEvent =
  | { type: 'usage'; data: MWTokenUsage & { stage: 'estimate' | 'final' } }
  | { type: 'complete'; data: MWSendResponse }
  | { type: 'error'; message: string }
