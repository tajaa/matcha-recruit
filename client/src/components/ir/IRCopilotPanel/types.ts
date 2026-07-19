import { type CopilotCard } from '../IRCopilotCard'

export type CopilotMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  message_type: 'text' | 'card' | 'event'
  content: string
  metadata: Record<string, unknown> | null
  created_by: string | null
  created_at: string
}

export type CopilotProgressStep = {
  key: string
  label: string
  status: 'done' | 'pending' | 'not_applicable'
  hint: string
}

/** Mirrors `services/ir_flow.close_progress`. */
export type CopilotProgress = {
  completed: number
  total: number
  percent: number
  steps: CopilotProgressStep[]
  next_step_key: string | null
  next_step_hint: string
  is_complete: boolean
}

/** Mirrors `services/ir_flow.copilot_evidence`. */
export type CopilotEvidence = {
  score: number
  threshold: number
  sufficient: boolean
  signals: string[]
  missing: string[]
  days_open: number
  max_days: number
  is_overdue: boolean
}

export type Transcript = {
  incident_id: string
  messages: CopilotMessage[]
  current_cards: CopilotCard[]
  summary: string | null
  open_questions: string[]
  progress: CopilotProgress | null
  evidence: CopilotEvidence | null
}

export interface Props {
  incidentId: string
  incidentStatus?: string
  reportedByName?: string | null
  reportedByEmail?: string | null
  onIncidentChanged?: () => void
  onOpenDocuments?: () => void
}
