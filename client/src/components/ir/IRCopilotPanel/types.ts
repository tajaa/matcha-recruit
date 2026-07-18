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

export type Transcript = {
  incident_id: string
  messages: CopilotMessage[]
  current_cards: CopilotCard[]
  summary: string | null
  open_questions: string[]
}

export interface Props {
  incidentId: string
  incidentStatus?: string
  reportedByName?: string | null
  reportedByEmail?: string | null
  onIncidentChanged?: () => void
  onOpenDocuments?: () => void
}
