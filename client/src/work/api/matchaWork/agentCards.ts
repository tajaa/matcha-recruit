import { api } from '../../../api/client'

// ── Agent cards (category 'agent') ──
//
// Backend: server/app/matcha/routes/matcha_work/agent_cards.py. A run starts on
// its own when an agent card is created or sent back from review; these are
// the read side (every result round) and the manual "Run again".

export type AgentLink = { retailer: string; url: string; price: number | null }
export type AgentReview = { quote: string; source_name: string; url: string; sentiment: 'pos' | 'neg' | 'mixed' }
export type AgentImage = { url: string; page_url: string; alt: string }

export type AgentPick = {
  name: string
  brand: string
  why: string[]
  price: { amount: number; currency: string; source_url: string } | null
  rating: { value: number; scale: number; count: number | null; source_url: string } | null
  reviews: AgentReview[]
  images: AgentImage[]
  buy_links: AgentLink[]
}

export type AgentResult = {
  schema: 'agent_result.v1'
  headline: string
  summary: string
  answer_type: 'recommendation' | 'answer'
  criteria: { name: string; why: string }[]
  top_pick: AgentPick | null
  alternatives: AgentPick[]
  sections: { heading: string; body_md: string }[]
  caveats: string[]
  sources: { title: string; url: string }[]
  confidence: 'high' | 'medium' | 'low'
  changes_from_previous: string | null
  warnings?: string[]
  round?: number
}

export type AgentRunStatus = 'queued' | 'running' | 'done' | 'failed'

export type AgentRun = {
  id: string
  round: number
  status: AgentRunStatus
  result: AgentResult | null
  error: string | null
  search_calls: number
  model_calls: number
  created_at: string | null
  started_at: string | null
  completed_at: string | null
  steps: { seq: number; kind: string; label: string; status: string }[]
}

export function listAgentRuns(projectId: string, taskId: string) {
  return api.get<{ runs: AgentRun[] }>(`/matcha-work/projects/${projectId}/tasks/${taskId}/agent-runs`)
}

export function rerunAgent(projectId: string, taskId: string) {
  return api.post<{ run_id: string; round: number; status: AgentRunStatus }>(
    `/matcha-work/projects/${projectId}/tasks/${taskId}/agent-runs`,
    {},
  )
}
