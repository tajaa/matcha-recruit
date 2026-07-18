import { api } from '../../../api/client'
import type { AgentEmail } from '../../types'

// ── Agent (email) ──

export function agentEmailStatus() {
  return api.get<{ connected: boolean; email: string | null }>('/matcha-work/agent/email/status')
}

export function agentConnectGmail() {
  return api.post<{ auth_url: string }>('/matcha-work/agent/email/connect')
}

export function agentDisconnectGmail() {
  return api.delete<{ status: string }>('/matcha-work/agent/email/disconnect')
}

export function agentFetchEmails() {
  return api.post<{ emails: AgentEmail[] }>('/matcha-work/agent/email/fetch')
}

export function agentDraftReply(emailId: string, instructions: string) {
  return api.post<{ draft_id: string; to: string; subject: string; body: string }>(
    '/matcha-work/agent/email/draft',
    { email_id: emailId, instructions }
  )
}

export function agentSendEmail(to: string, subject: string, body: string, replyToId?: string) {
  return api.post<{ message_id: string; to: string; subject: string }>(
    '/matcha-work/agent/email/send',
    { to, subject, body, reply_to_id: replyToId }
  )
}
