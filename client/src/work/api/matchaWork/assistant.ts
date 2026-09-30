import { api } from '../../../api/client'
import type { AgentChatResultV2, AgentProgressStep } from '../../types'

// ── Espresso assistant ──
//
// Backend: server/app/matcha/routes/matcha_work/assistant.py. The
// conversation itself runs over the channel socket (every message in the
// private conversation is addressed to Espresso); these are the rest: open
// the conversation, read a run, and switch abilities on and off.

export type AssistantDisclosure = { version: string; title: string; body: string[] }

export type AssistantAbility = {
  key: string
  label: string
  /** Reading the web and comparing things to buy need nothing switched on. */
  always_on: boolean
  enabled: boolean
  available: boolean
  /** Why it can't be used yet, in the person's terms. */
  reason: string | null
  needs_consent: boolean
  needs_connection: boolean
  missing_scopes: string[]
  private_only: boolean
  /** Whether it can act outward (send, invite, book), not just look. */
  acts: boolean
  disclosure: AssistantDisclosure | null
  /** They agreed to an older disclosure than the current one. */
  consent_outdated: boolean
  settings: { contact?: { name?: string; phone?: string; email?: string } }
}

export type AssistantAbilities = {
  abilities: AssistantAbility[]
  google: { connected: boolean; scopes: string[] }
  /** 'dry_run' until the server is switched to 'live': nothing leaves the system. */
  commit_mode: 'dry_run' | 'live'
}

export type AssistantRun = {
  id: string
  status: 'queued' | 'running' | 'done' | 'failed'
  surface: 'assistant' | 'project_chat'
  abilities: string[]
  result: AgentChatResultV2 | null
  error: string | null
  model_calls: number
  search_calls: number
  created_at: string | null
  started_at: string | null
  completed_at: string | null
  steps: (AgentProgressStep & { created_at: string | null })[]
}

/** The caller's private conversation with Espresso, created on first use. */
export function ensureAssistantChannel() {
  return api.post<{ channel_id: string }>('/matcha-work/assistant/channel')
}

export function getAssistantRun(runId: string) {
  return api.get<AssistantRun>(`/matcha-work/assistant/runs/${runId}`)
}

export function listAssistantAbilities() {
  return api.get<AssistantAbilities>('/matcha-work/assistant/abilities')
}

export function enableAssistantAbility(
  key: string,
  body: { consent_version: string | null; settings?: AssistantAbility['settings'] },
) {
  return api.put<{ key: string; enabled: boolean }>(`/matcha-work/assistant/abilities/${key}`, body)
}

export function disableAssistantAbility(key: string) {
  return api.delete<{ key: string; enabled: boolean }>(`/matcha-work/assistant/abilities/${key}`)
}

/** Which Google permissions to ask for on top of reading and sending mail. */
const GOOGLE_ABILITIES: Record<string, string[]> = {
  email: ['email_organize'],
  calendar: ['calendar'],
}

/** Start Google's consent for what `key` needs. Opens in a popup by the caller. */
export function connectGoogleFor(key: string) {
  return api.post<{ auth_url: string }>('/matcha-work/agent/email/connect', {
    abilities: GOOGLE_ABILITIES[key] ?? [],
  })
}
