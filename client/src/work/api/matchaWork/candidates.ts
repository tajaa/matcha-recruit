import { api } from '../../../api/client'
import type { MWProject, ResumeCandidate } from '../../types'
import { uploadFilesStream, type UploadStreamCallbacks } from './_base'

// ── Recruiting project ──

export function uploadProjectResumes(
  projectId: string,
  files: File[],
  callbacks: UploadStreamCallbacks,
): AbortController {
  return uploadFilesStream(`/matcha-work/projects/${projectId}/resume/upload`, files, callbacks)
}

export function generatePlaceholderQuestions(placeholders: { placeholder: string; label: string }[]) {
  return api.post<{ questions: { placeholder: string; label: string; question: string }[] }>(
    '/matcha-work/projects/placeholder-questions', { placeholders }
  )
}

export function extractPlaceholderValue(input: string, placeholder: string, context: string) {
  return api.post<{ value: string }>('/matcha-work/projects/extract-value', { input, placeholder, context })
}

export function analyzeProjectCandidates(projectId: string) {
  return api.post<{ analyzed: number; candidates: ResumeCandidate[] }>(
    `/matcha-work/projects/${projectId}/resume/analyze`
  )
}

export interface ScreeningAttribute {
  score: number
  evidence: string[]
  notes?: string | null
}

export interface ScreeningAnalysis {
  communication_clarity: ScreeningAttribute
  engagement_energy: ScreeningAttribute
  critical_thinking: ScreeningAttribute
  professionalism: ScreeningAttribute
  overall_score: number
  recommendation: 'strong_pass' | 'pass' | 'borderline' | 'fail'
  summary: string
  analyzed_at: string
}

export interface InterviewDetail {
  id: string
  interview_type: string
  status: string
  transcript?: string | null
  screening_analysis?: ScreeningAnalysis | null
  created_at: string
  completed_at?: string | null
}

export function getInterview(interviewId: string) {
  return api.get<InterviewDetail>(`/interviews/${interviewId}`)
}

export function sendProjectInterviews(
  projectId: string,
  candidateIds: string[],
  positionTitle?: string,
  customMessage?: string,
) {
  return api.post<{
    sent: { id: string; name: string; email: string; interview_id: string; email_sent: boolean }[]
    failed: { id: string; error: string }[]
  }>(`/matcha-work/projects/${projectId}/resume/send-interviews`, {
    candidate_ids: candidateIds,
    position_title: positionTitle,
    custom_message: customMessage,
  })
}

export function syncProjectInterviews(projectId: string) {
  return api.post<{ updated: number }>(
    `/matcha-work/projects/${projectId}/resume/sync-interviews`
  )
}

export function toggleProjectShortlist(projectId: string, candidateId: string) {
  return api.post(`/matcha-work/projects/${projectId}/shortlist/${candidateId}`)
}

export function toggleProjectDismiss(projectId: string, candidateId: string) {
  return api.post(`/matcha-work/projects/${projectId}/dismiss/${candidateId}`)
}

export function rejectProjectCandidate(
  projectId: string,
  candidateId: string,
  opts: { rejectionReason?: string; customMessage?: string; sendEmail?: boolean } = {},
) {
  return api.post<{ project: MWProject; email_sent: boolean }>(
    `/matcha-work/projects/${projectId}/reject/${candidateId}`,
    {
      rejection_reason: opts.rejectionReason,
      custom_message: opts.customMessage,
      send_email: opts.sendEmail ?? true,
    },
  )
}

export function updateProjectPosting(projectId: string, posting: Record<string, unknown>) {
  return api.put(`/matcha-work/projects/${projectId}/posting`, posting)
}

export function populatePostingFromChat(projectId: string, content: string) {
  return api.post<MWProject>(
    `/matcha-work/projects/${projectId}/posting/from-chat`,
    { content }
  )
}
