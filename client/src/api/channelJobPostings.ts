import { api } from './client'
import type { ParsedResume } from './profileResume'

export type JobPostingStatus =
  | 'pending_approval'
  | 'draft'
  | 'active'
  | 'closed'
  | 'rejected'

export interface JobPostingSummary {
  id: string
  channel_id: string
  title: string
  status: JobPostingStatus
  subscription_status: string | null
  applicant_count: number
  invited_count: number
  open_to_all?: boolean
  posted_by?: string
  approved_by?: string | null
  approved_at?: string | null
  created_at: string
}

export interface JobPostingDetail extends JobPostingSummary {
  description: string | null
  requirements: string | null
  compensation_summary: string | null
  location: string | null
  paid_through: string | null
  posted_by: string
  open_to_all: boolean
  i_can_apply?: boolean
  approved_by: string | null
  approved_at: string | null
  rejected_reason: string | null
  my_invitation: { invited_at: string; viewed_at: string | null } | null
  my_application: { id: string; status: string; submitted_at: string } | null
}

export interface PendingApprovalSummary {
  id: string
  title: string
  description: string | null
  location: string | null
  compensation_summary: string | null
  created_at: string
  channel_id: string
  channel_name: string
  posted_by: string
  posted_by_name: string
}

export interface ApplicationSummary {
  id: string
  applicant_id: string
  applicant_name: string
  applicant_email: string
  status: string
  cover_letter: string | null
  resume_snapshot?: ParsedResume | null
  resume_locked?: boolean
  submitted_at: string
  reviewed_at: string | null
}

export interface OpenPostingSummary {
  id: string
  title: string
  location: string | null
  compensation_summary: string | null
  created_at: string
  already_applied: boolean
}

export interface JobPostingFee {
  fee_cents: number | null
  default_used: boolean
}

export interface MyJobInvitation {
  posting_id: string
  channel_id: string
  channel_name: string
  posting_title: string
  invited_at: string
  viewed_at: string | null
}

export const listJobPostings = (channelId: string) =>
  api.get<JobPostingSummary[]>(`/channels/${channelId}/job-postings`)

export const getJobPosting = (channelId: string, postingId: string) =>
  api.get<JobPostingDetail>(`/channels/${channelId}/job-postings/${postingId}`)

export const createJobPosting = (channelId: string, data: {
  title: string
  description?: string
  requirements?: string
  compensation_summary?: string
  location?: string
  open_to_all?: boolean
}) => api.post<JobPostingSummary>(`/channels/${channelId}/job-postings`, data)

export const updateJobPosting = (channelId: string, postingId: string, data: {
  title?: string
  description?: string
  requirements?: string
  compensation_summary?: string
  location?: string
}) => api.patch<JobPostingDetail>(`/channels/${channelId}/job-postings/${postingId}`, data)

export const createJobPostingCheckout = (channelId: string, postingId: string) =>
  api.post<{ checkout_url: string }>(`/channels/${channelId}/job-postings/${postingId}/checkout`)

export const cancelJobPosting = (channelId: string, postingId: string) =>
  api.post<{ ok: boolean }>(`/channels/${channelId}/job-postings/${postingId}/cancel`)

export const closeJobPosting = (channelId: string, postingId: string) =>
  api.post<{ ok: boolean }>(`/channels/${channelId}/job-postings/${postingId}/close`)

export const inviteToPosting = (channelId: string, postingId: string, userIds: string[]) =>
  api.post<{ ok: boolean }>(`/channels/${channelId}/job-postings/${postingId}/invite`, { user_ids: userIds })

export const listApplicants = (channelId: string, postingId: string) =>
  api.get<ApplicationSummary[]>(`/channels/${channelId}/job-postings/${postingId}/applicants`)

export const submitApplication = (channelId: string, postingId: string, coverLetter?: string) =>
  api.post<{ ok: boolean }>(`/channels/${channelId}/job-postings/${postingId}/apply`, {
    cover_letter: coverLetter || null,
  })

export const withdrawApplication = (channelId: string, postingId: string) =>
  api.post<{ ok: boolean }>(`/channels/${channelId}/job-postings/${postingId}/withdraw`)

export const updateApplicationStatus = (
  channelId: string,
  postingId: string,
  applicationId: string,
  status: string,
  reviewerNotes?: string
) =>
  api.patch<{ ok: boolean }>(`/channels/${channelId}/job-postings/${postingId}/applicants/${applicationId}`, {
    status,
    reviewer_notes: reviewerNotes || null,
  })

export const getMyJobInvitations = () =>
  api.get<MyJobInvitation[]>('/channels/job-postings/my-invitations')

export const getMyPendingApprovals = () =>
  api.get<PendingApprovalSummary[]>('/channels/job-postings/my-pending-approvals')

export const approveJobPosting = (channelId: string, postingId: string) =>
  api.post<JobPostingDetail>(`/channels/${channelId}/job-postings/${postingId}/approve`)

export const rejectJobPosting = (channelId: string, postingId: string, reason?: string) =>
  api.post<JobPostingDetail>(`/channels/${channelId}/job-postings/${postingId}/reject`, {
    reason: reason ?? null,
  })

export const listOpenPostings = (channelId: string) =>
  api.get<OpenPostingSummary[]>(`/channels/${channelId}/open-postings`)

export const getJobPostingFee = (channelId: string) =>
  api.get<JobPostingFee>(`/channels/${channelId}/job-posting-fee`)
