import { api } from './client'

export interface JobPostingSummary {
  id: string
  channel_id: string
  title: string
  status: 'draft' | 'active' | 'closed'
  subscription_status: string | null
  applicant_count: number
  invited_count: number
  created_at: string
}

export interface JobPostingDetail extends JobPostingSummary {
  description: string | null
  requirements: string | null
  compensation_summary: string | null
  location: string | null
  paid_through: string | null
  posted_by: string
  my_invitation: { invited_at: string; viewed_at: string | null } | null
  my_application: { id: string; status: string; submitted_at: string } | null
}

export interface ApplicationSummary {
  id: string
  applicant_id: string
  applicant_name: string
  applicant_email: string
  status: string
  cover_letter: string | null
  submitted_at: string
  reviewed_at: string | null
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
