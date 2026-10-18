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
  commit_mode?: 'dry_run' | 'live'
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
  /** Default for abilities without their own mode. Calendar consent enables live changes. */
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

/** One of the person's sessions with Espresso: its own channel and history.
 *  `main` is the one `ensureAssistantChannel` opens; it can't be archived. */
export type AssistantConversation = {
  id: string
  title: string
  updated_at: string | null
  archived: boolean
  main: boolean
}

export type AssistantConversationList = { conversations: AssistantConversation[]; has_more: boolean }

/** 50 at a time, most recently active first. */
export function listAssistantConversations(offset = 0, archived = false) {
  return api.get<AssistantConversationList>(
    `/matcha-work/assistant/conversations?offset=${offset}&archived=${archived}`,
  )
}

/** `requestId` makes a retried create return the same session. */
export function createAssistantConversation(title: string, requestId: string) {
  return api.post<{ channel_id: string }>('/matcha-work/assistant/conversations', {
    title, request_id: requestId,
  })
}

export function renameAssistantConversation(id: string, title: string) {
  return api.patch<AssistantConversation>(`/matcha-work/assistant/conversations/${id}`, { title })
}

/** Hides a session from the list; every message is kept. */
export function archiveAssistantConversation(id: string) {
  return api.post<AssistantConversation>(`/matcha-work/assistant/conversations/${id}/archive`)
}

export function restoreAssistantConversation(id: string) {
  return api.post<AssistantConversation>(`/matcha-work/assistant/conversations/${id}/restore`)
}

/** A file given to Espresso is private; its attachment URL names it. */
export const PRIVATE_INPUT_SCHEME = 'espresso-input:'

export function privateInputId(url: string | null | undefined): string | null {
  if (!url || !url.startsWith(PRIVATE_INPUT_SCHEME)) return null
  const id = url.slice(PRIVATE_INPUT_SCHEME.length)
  return id || null
}

/** A five-minute link to one of the caller's own Espresso files. */
export function getAssistantInputLink(inputId: string) {
  return api.get<{ url: string; filename: string; content_type: string; expires_in: number }>(
    `/matcha-work/assistant/inputs/${inputId}/url`,
  )
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
