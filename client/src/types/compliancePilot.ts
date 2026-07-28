// Types for the agentic Compliance Pilot (client/src/api/admin/compliancePilot.ts
// hosts the pre-existing legacy-mode types as debt — see client/CLAUDE.md's
// "don't export a domain type from an api module" rule; these are new, so they
// live here instead of adding to that debt).
import type { ChatHandlers as SharedChatHandlers } from '../api/sse'

// The agentic loop's citations are DB-sourced records, not model-generated
// {point, cited_ids} pairs — a distinct shape, hence a distinct type/field
// (never render one under the other's key).
export type CitationRecord = {
  cid: string
  summary: string
  citation?: string | null
  source_url?: string | null
  state?: string | null
  city?: string | null
  jurisdiction_name?: string | null
}

// One tool call in an agentic Pilot turn. Mirrors matcha-work's HuumeStep —
// same shape, kept as a separate local type since `components/ui` (where its
// renderer lives) must not import from `work/` (client/CLAUDE.md boundary rule).
export type PilotStep = {
  seq: number
  tool: string
  kind: 'read' | 'staged' | 'write' | 'finish'
  label: string
  status: 'ok' | 'rejected' | 'error'
  detail?: string
  args?: unknown
  result?: unknown
}

// Agentic mode's turn result — a different shape from the legacy ChatResult
// (the terminal frame is named `agent_result`, aliased to `result` by the
// shared SSE parser).
export type AgentChatResult = {
  message: string
  steps: PilotStep[]
  citations: CitationRecord[]
  proposal_action_ids: string[]
  token_usage?: Record<string, unknown>
  model_calls?: number
  error?: string
}
export type AgentChatHandlers = SharedChatHandlers<AgentChatResult, PilotStep>
