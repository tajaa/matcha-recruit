import { api } from '../../../api/client'

// ── AI connectors (Claude / ChatGPT → Matcha, on the person's own plan) ──
//
// Backend: server/app/matcha/routes/matcha_work/connectors.py. The OAuth
// protocol endpoints themselves live at /api/oauth/* (MCP SDK); these are the
// person-facing pieces: consent, the connected-assistants list, and the
// "Research with…" deep link for a research card.

export type ConnectorKind = 'claude' | 'chatgpt' | 'claude_code' | 'other'

export type ConnectorGrant = {
  client_id: string
  client_name: string
  kind: ConnectorKind
  connected_at: string | null
  last_used_at: string | null
}

export type ConnectorsState = {
  mcp_url: string
  grants: ConnectorGrant[]
  connected: Record<'claude' | 'chatgpt' | 'claude_code', boolean>
  claude_code_command: string
}

export type ConsentDescription = {
  client_name: string
  client_kind: ConnectorKind
  redirect_host: string
  scopes: string[]
}

export type ResearchLaunch = {
  client: string
  url: string | null
  prompt: string
  command: string | null
}

export function listConnectors() {
  return api.get<ConnectorsState>('/matcha-work/connectors')
}

export function disconnectConnector(clientId: string) {
  return api.delete<{ disconnected: boolean }>(`/matcha-work/connectors/${encodeURIComponent(clientId)}`)
}

export function describeConnectorConsent(request: string) {
  return api.get<ConsentDescription>(`/matcha-work/connectors/consent?request=${encodeURIComponent(request)}`)
}

export function decideConnectorConsent(request: string, approve: boolean) {
  return api.post<{ redirect_url: string }>('/matcha-work/connectors/consent', { request, approve })
}

export function launchResearchWith(projectId: string, taskId: string, client: 'claude' | 'chatgpt' | 'claude_code') {
  return api.post<ResearchLaunch>(
    `/matcha-work/projects/${projectId}/tasks/${taskId}/research-launch`,
    { client },
  )
}
