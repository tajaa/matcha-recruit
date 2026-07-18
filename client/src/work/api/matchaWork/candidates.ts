import { api, ensureFreshToken } from '../../../api/client'
import type { MWProject, MWStreamEvent, ResumeCandidate } from '../../types'
import { BASE } from './_base'

// ── Recruiting project ──

export function uploadProjectResumes(
  projectId: string,
  files: File[],
  callbacks: {
    onEvent: (event: MWStreamEvent) => void
    onComplete: (data: Record<string, unknown>) => void
    onError: (err: string) => void
  },
): AbortController {
  const ctrl = new AbortController()
  const timeout = setTimeout(() => ctrl.abort('timeout'), 300_000)

  ;(async () => {
    const token = await ensureFreshToken()
    const form = new FormData()
    files.forEach((f) => form.append('files', f))

    fetch(`${BASE}/matcha-work/projects/${projectId}/resume/upload`, {
      method: 'POST',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: form,
      signal: ctrl.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          clearTimeout(timeout)
          const text = await res.text().catch(() => res.statusText)
          callbacks.onError(`${res.status}: ${text}`)
          return
        }
        const reader = res.body?.getReader()
        if (!reader) { clearTimeout(timeout); callbacks.onError('No response body'); return }
        const decoder = new TextDecoder()
        let buf = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n')
          buf = lines.pop() ?? ''
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6).trim()
            if (raw === '[DONE]') { clearTimeout(timeout); return }
            try {
              const event = JSON.parse(raw)
              callbacks.onEvent(event as MWStreamEvent)
              if (event.type === 'complete') { clearTimeout(timeout); callbacks.onComplete(event.data); return }
              if (event.type === 'error') { clearTimeout(timeout); callbacks.onError(event.message); return }
            } catch {}
          }
        }
        clearTimeout(timeout)
      })
      .catch((e) => {
        clearTimeout(timeout)
        if (ctrl.signal.aborted && ctrl.signal.reason === 'timeout') {
          callbacks.onError('Request timed out.')
        } else if (!ctrl.signal.aborted) {
          callbacks.onError(e instanceof Error ? e.message : 'Upload failed')
        }
      })
  })()

  return ctrl
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
