import { api } from '../../../api/client'
import type { AgentEmail } from '../../types'

// ── Agent (email) ──

export function agentEmailStatus() {
  return api.get<{ connected: boolean; email: string | null; snapshot_max_emails: number }>('/matcha-work/agent/email/status')
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

export type AgentDraft = { draft_id: string | null; to: string; subject: string; body: string; thread_id: string | null; in_reply_to: string | null }
export type AgentTriageBucket = { email_id: string; bucket: 'needs_reply' | 'action' | 'fyi' | 'newsletter'; reason: string }
export type AgentSnapshotResult = { files: { id: string; filename: string }[]; skipped: { email_id: string; reason: string }[] }

export function agentSummarizeEmail(emailId: string) {
  return api.post<{ email_id: string; summary: string }>('/matcha-work/agent/email/summarize', { email_id: emailId })
}

export function agentTriageEmails(emailIds?: string[]) {
  return api.post<{ buckets: AgentTriageBucket[] }>('/matcha-work/agent/email/triage', emailIds === undefined ? {} : { email_ids: emailIds })
}

export function agentDraftReply(emailId: string, instructions?: string) {
  return api.post<AgentDraft>(
    '/matcha-work/agent/email/draft',
    { email_id: emailId, ...(instructions ? { instructions } : {}) }
  )
}

export function agentSendEmail(body: { to: string; subject: string; body: string; reply_to_id?: string; thread_id?: string | null; in_reply_to?: string | null; draft_id?: string | null }) {
  return api.post<{ message_id: string; to: string; subject: string }>(
    '/matcha-work/agent/email/send',
    body
  )
}

export function agentSnapshotEmails(emailIds: string[], projectId: string, taskId: string) {
  return api.post<AgentSnapshotResult>('/matcha-work/agent/email/snapshot', { email_ids: emailIds, project_id: projectId, task_id: taskId })
}
