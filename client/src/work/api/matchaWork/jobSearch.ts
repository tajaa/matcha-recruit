import { api } from '../../../api/client'
import type { AssistantDisclosure } from './assistant'

// Espresso Job search (`/matcha-work/job-searches`), the same API the macOS
// app's Job search uses. The server finds, screens, prices and ranks the jobs,
// and drafts how to approach the best ones; the page shows them and keeps the
// person's own status and notes. Personal Espresso accounts only.

export type JobSearchStatus =
  | 'queued' | 'planning' | 'discovering' | 'screening' | 'enriching' | 'approaching'
  | 'done' | 'failed' | 'cancelled'

export type RemotePreference = 'any' | 'remote_only' | 'onsite_only'

/** How much each part counts in the ranking (0..1 each; the server renormalizes). */
export interface JobWeights {
  base: number
  bonus: number
  equity: number
  fit: number
}

export interface JobCriteria {
  titles: string[]
  locations: string[]
  remote: RemotePreference
  base_floor: number | null
  currency: string
  exclude_companies: string[]
  deal_breakers: string[]
}

export interface JobSearchProgress {
  note?: string | null
  found?: number | null
  relevant?: number | null
  posted_pay?: number | null
}

export interface JobSearchSummary {
  id: string
  title: string
  ask: string
  status: JobSearchStatus | string
  progress: JobSearchProgress | null
  error: string | null
  lead_count: number
  posted_pay_count: number
  weights: JobWeights | null
  use_resume: boolean
  created_at: string | null
  /** The lowest fit (out of 5) the search reads, ranks first and drafts: 4
   *  for its first pass (3 when nothing scored 4), 3 once widened. */
  fit_floor: number | null
}

export interface JobLeadSummary {
  id: string
  title: string
  company: string
  location: string
  remote: boolean | null
  source_url: string | null
  apply_url: string | null
  posted_text: string | null
  comp_line: string
  /** `posted`, `mentioned` or `not_disclosed`. */
  comp_status: string
  fit_score: number | null
  screen_status: string
  rank: number | null
  rank_band: number | null
  flags: string[]
  /** `new`, `saved`, `applied` or `dismissed`. */
  user_state: string
  /** `none`, `queued`, `drafting`, `done` or `failed`. */
  approach_status: string
  email_draft_id: string | null
  email_drafted_at: string | null
  email_sent_at: string | null
}

export interface JobSearchDetail extends JobSearchSummary {
  leads: JobLeadSummary[]
  fingerprint: string
}

export interface JobSearchStatusView {
  id: string
  status: string
  progress: JobSearchProgress | null
  error: string | null
  lead_count: number
  fingerprint: string
}

export interface JobEvidence {
  quote?: string | null
  origin?: string | null
  url?: string | null
}

export interface JobCompPart {
  status?: string | null
  kind?: string | null
  min?: number | null
  max?: number | null
  currency?: string | null
  period?: string | null
  annual_min?: number | null
  annual_max?: number | null
  pct_min?: number | null
  pct_max?: number | null
  evidence?: JobEvidence | null
}

export interface JobQuestion {
  key?: string | null
  label?: string | null
  question?: string | null
}

export interface JobApproach {
  summary?: string | null
  channel?: string | null
  steps?: string[]
  talking_points?: string[]
  negotiation?: string[]
  contacts?: { name: string; role?: string | null; source_url?: string | null }[]
  outreach?: { to_email?: string | null; subject?: string | null; body?: string | null } | null
  answers?: { question_key?: string | null; question: string; answer: string; likely?: boolean | null }[]
  unanswered?: JobQuestion[]
  cover_letter?: string | null
  sources?: string[]
}

export interface JobLeadDetail extends JobLeadSummary {
  description: string
  comp: { base?: JobCompPart | null; bonus?: JobCompPart | null; equity?: JobCompPart | null } | null
  pay_law_hint: string | null
  screen_reason: string | null
  fit_reasons: string[]
  approach: JobApproach | null
  notes: string
}

export interface JobSearchUsage {
  limit: number
  used: number
  remaining: number
  resets_at: string | null
}

export interface JobSearchList {
  searches: JobSearchSummary[]
  usage: JobSearchUsage | null
  consent: { granted: boolean; disclosure: AssistantDisclosure | null } | null
  available: boolean
}

export interface JobSearchCreate {
  /** Kept across retries of one start, so a retry after a dropped connection
   *  gets back the search it started instead of starting a second one. */
  request_id: string
  title: string
  ask: string
  criteria: JobCriteria
  weights: JobWeights | null
  use_resume: boolean
  consent_version: string | null
}

export interface JobEmailDraftResult {
  draft_id: string
  to: string
  subject: string
  created: boolean
  lead: JobLeadDetail | null
}

const BASE = '/matcha-work/job-searches'
const searchPath = (id: string) => `${BASE}/${encodeURIComponent(id)}`
const leadPath = (searchId: string, leadId: string) => `${searchPath(searchId)}/leads/${encodeURIComponent(leadId)}`

export const listJobSearches = () => api.get<JobSearchList>(BASE)
export const createJobSearch = (body: JobSearchCreate) => api.post<JobSearchSummary>(BASE, body)
export const getJobSearch = (id: string) => api.get<JobSearchDetail>(searchPath(id))
export const getJobSearchStatus = (id: string) => api.get<JobSearchStatusView>(`${searchPath(id)}/status`)
export const getJobLead = (searchId: string, leadId: string) => api.get<JobLeadDetail>(leadPath(searchId, leadId))
export const updateJobLead = (searchId: string, leadId: string, patch: { user_state?: string; notes?: string }) =>
  api.patch<JobLeadDetail>(leadPath(searchId, leadId), patch)
/** Re-rank with new weights. Free: no search is spent. */
export const rerankJobSearch = (id: string, weights: JobWeights) =>
  api.put<JobSearchDetail>(`${searchPath(id)}/weights`, weights)
/** Add a finished search's 3/5 matches. Free, once a search. */
export const widenJobSearch = (id: string) => api.post<JobSearchDetail>(`${searchPath(id)}/widen`)
export const redraftJobApproach = (searchId: string, leadId: string) =>
  api.post<JobSearchDetail>(`${leadPath(searchId, leadId)}/approach`)
/** Put a job's first message in the person's Gmail drafts. Nothing is sent. */
export const draftJobEmail = (searchId: string, leadId: string) =>
  api.post<JobEmailDraftResult>(`${leadPath(searchId, leadId)}/email-draft`)
export const cancelJobSearch = (id: string) => api.post<JobSearchDetail>(`${searchPath(id)}/cancel`)
export const deleteJobSearch = (id: string) => api.delete<{ deleted: boolean }>(searchPath(id))
