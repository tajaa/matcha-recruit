import { api, ApiError } from '../../../api/client'

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

/** A purchase approved in the project chat. v1 is a handoff: nothing was
 *  charged, the person finishes checkout at the link. */
export type AgentPurchase = {
  id: string
  run_id: string | null
  item_name: string
  retailer: string | null
  checkout_url: string
  amount: number | null
  currency: string | null
  card_last4: string
  status: 'handoff' | 'cancelled'
  created_at: string | null
}

export function listAgentRuns(projectId: string, taskId: string) {
  return api.get<{ runs: AgentRun[]; purchases?: AgentPurchase[] }>(
    `/matcha-work/projects/${projectId}/tasks/${taskId}/agent-runs`,
  )
}

export function rerunAgent(projectId: string, taskId: string) {
  return api.post<{ run_id: string; round: number; status: AgentRunStatus }>(
    `/matcha-work/projects/${projectId}/tasks/${taskId}/agent-runs`,
    {},
  )
}

// ── Saved payment cards (agent-card purchases; admin-only in v1) ──
//
// Backend: server/app/matcha/routes/matcha_work/payment_cards.py. The number is
// sent once, encrypted server-side, and never returned. There is no CVV field.

export type PaymentCard = {
  id: string
  label: string
  brand: 'visa' | 'mastercard' | 'amex' | 'discover' | 'card'
  last4: string
  exp_month: number
  exp_year: number
  created_at: string | null
}

export function listPaymentCards() {
  return api.get<{ enabled: boolean; configured: boolean; cards: PaymentCard[] }>('/matcha-work/payment-cards')
}

export function addPaymentCard(body: { number: string; exp_month: number; exp_year: number; label: string }) {
  return api.post<PaymentCard>('/matcha-work/payment-cards', body)
}

export function deletePaymentCard(cardId: string) {
  return api.delete<void>(`/matcha-work/payment-cards/${cardId}`)
}

/** Server `detail` -> one readable line (plan / monthly cap / plain string). */
export function agentErrorMessage(e: unknown): string {
  if (e instanceof ApiError && e.body && typeof e.body === 'object' && 'detail' in e.body) {
    const detail = (e.body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object') {
      const d = detail as Record<string, unknown>
      if (d.code === 'plan_required') return 'Agent cards need the Pro plan.'
      if (d.code === 'agent_run_limit') {
        const resets = typeof d.resets_at === 'string' ? new Date(d.resets_at).toLocaleDateString() : 'next month'
        return `You've used all ${d.limit} agent runs this month. They reset ${resets}.`
      }
      if (typeof d.message === 'string') return d.message
    }
  }
  return e instanceof Error ? e.message : 'Something went wrong.'
}
