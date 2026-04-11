import { api, ensureFreshToken } from './client'
import type {
  MWThread,
  MWThreadDetail,
  MWCreateResponse,
  MWSendResponse,
  MWStreamEvent,
  ResearchTask,
  ResearchInput,
} from '../types/matcha-work'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

// ── Threads ──

export function listThreads(status?: string) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return api.get<MWThread[]>(`/matcha-work/threads${qs}`)
}

export function getThread(id: string) {
  return api.get<MWThreadDetail>(`/matcha-work/threads/${id}`)
}

export function createThread(title?: string, initial_message?: string) {
  return api.post<MWCreateResponse>('/matcha-work/threads', {
    title,
    initial_message,
  })
}

// ── Thread actions ──

export function pinThread(id: string, is_pinned = true) {
  return api.post<MWThread>(`/matcha-work/threads/${id}/pin`, { is_pinned })
}

export function setNodeMode(id: string, node_mode: boolean) {
  return api.post<MWThread>(`/matcha-work/threads/${id}/node-mode`, { node_mode })
}

export function setComplianceMode(id: string, compliance_mode: boolean) {
  return api.post<MWThread>(`/matcha-work/threads/${id}/compliance-mode`, { compliance_mode })
}

export function setPayerMode(id: string, payer_mode: boolean) {
  return api.post<MWThread>(`/matcha-work/threads/${id}/payer-mode`, { payer_mode })
}

export function archiveThread(id: string) {
  return api.delete(`/matcha-work/threads/${id}`)
}

export function updateTitle(id: string, title: string) {
  return api.patch<MWThread>(`/matcha-work/threads/${id}`, { title })
}

// ── PDF ──

export function getPdf(id: string, version?: number) {
  const qs = version != null ? `?version=${version}` : ''
  return api.get<{ pdf_url: string; version: number }>(
    `/matcha-work/threads/${id}/pdf${qs}`
  )
}

export function getPdfProxyUrl(id: string, version?: number) {
  const qs = version != null ? `?version=${version}` : ''
  return `${BASE}/matcha-work/threads/${id}/pdf/proxy${qs}`
}

// ── Presentation ──

export function generatePresentation(threadId: string) {
  return api.post<{
    thread_id: string
    version: number
    current_state: Record<string, unknown>
    slide_count: number
    generated_at: string
  }>(`/matcha-work/threads/${threadId}/presentation/generate`)
}

export function getPresentationPdf(threadId: string) {
  return api.get<{ pdf_url: string }>(
    `/matcha-work/threads/${threadId}/presentation/pdf`
  )
}

export function uploadPresentationImages(threadId: string, files: File[]) {
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  return api.upload<{ images: string[]; uploaded_count: number }>(
    `/matcha-work/threads/${threadId}/images`,
    form
  )
}

export function removePresentationImage(threadId: string, url: string) {
  return api.delete<{ images: string[] }>(
    `/matcha-work/threads/${threadId}/images?url=${encodeURIComponent(url)}`
  )
}

// ── Resume upload ──

export function uploadResumes(
  threadId: string,
  files: File[],
  callbacks: {
    onEvent: (event: MWStreamEvent) => void
    onComplete: (data: MWSendResponse) => void
    onError: (err: string) => void
  },
): AbortController {
  const ctrl = new AbortController()
  const timeout = setTimeout(() => ctrl.abort('timeout'), 300_000) // 5 min for large batches

  ;(async () => {
    const token = await ensureFreshToken()
    const form = new FormData()
    files.forEach((f) => form.append('files', f))

    fetch(`${BASE}/matcha-work/threads/${threadId}/resume/upload`, {
      method: 'POST',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
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
        if (!reader) {
          clearTimeout(timeout)
          callbacks.onError('No response body')
          return
        }

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
            if (raw === '[DONE]') {
              clearTimeout(timeout)
              return
            }

            try {
              const event: MWStreamEvent = JSON.parse(raw)
              callbacks.onEvent(event)
              if (event.type === 'complete') {
                clearTimeout(timeout)
                callbacks.onComplete(event.data)
                return
              }
              if (event.type === 'error') {
                clearTimeout(timeout)
                callbacks.onError(event.message)
                return
              }
            } catch {
              /* skip malformed */
            }
          }
        }
        clearTimeout(timeout)
      })
      .catch((e) => {
        clearTimeout(timeout)
        if (ctrl.signal.aborted) {
          if (ctrl.signal.reason === 'timeout') {
            callbacks.onError('Request timed out. Please try again.')
          }
        } else {
          callbacks.onError(e instanceof Error ? e.message : 'Upload failed')
        }
      })
  })()

  return ctrl
}

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
  return api.post<{ emails: import('../types/matcha-work').AgentEmail[] }>('/matcha-work/agent/email/fetch')
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

// ── Projects (top-level) ──

export function listProjects(status?: string) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return api.get<import('../types/matcha-work').MWProject[]>(`/matcha-work/projects${qs}`)
}

export function createProjectNew(title: string, projectType: string = 'general') {
  return api.post<import('../types/matcha-work').MWProject>('/matcha-work/projects', { title, project_type: projectType })
}

export function getProjectDetail(id: string) {
  return api.get<import('../types/matcha-work').MWProject>(`/matcha-work/projects/${id}`)
}

export function updateProjectMeta(id: string, updates: Record<string, unknown>) {
  return api.patch<import('../types/matcha-work').MWProject>(`/matcha-work/projects/${id}`, updates)
}

export function archiveProjectById(id: string) {
  return api.delete(`/matcha-work/projects/${id}`)
}

export function addProjectSectionNew(projectId: string, section: { title?: string; content: string; source_message_id?: string }) {
  return api.post<{ section: { id: string } }>(`/matcha-work/projects/${projectId}/sections`, section)
}

export function updateProjectSectionNew(projectId: string, sectionId: string, updates: { title?: string; content?: string }) {
  return api.put(`/matcha-work/projects/${projectId}/sections/${sectionId}`, updates)
}

export function deleteProjectSectionNew(projectId: string, sectionId: string) {
  return api.delete(`/matcha-work/projects/${projectId}/sections/${sectionId}`)
}

export function reorderProjectSectionsNew(projectId: string, sectionIds: string[]) {
  return api.put(`/matcha-work/projects/${projectId}/sections/reorder`, { section_ids: sectionIds })
}

export function editDiagramAI(projectId: string, sectionId: string, instruction: string, region?: { x: number; y: number; width: number; height: number }) {
  return api.post<import('../types/matcha-work').MWProject>(`/matcha-work/projects/${projectId}/sections/${sectionId}/edit-diagram`, { instruction, ...(region ? { region } : {}) })
}

export function editDiagramText(projectId: string, sectionId: string, edits: { old_text: string; new_text: string }[]) {
  return api.post<import('../types/matcha-work').MWProject>(`/matcha-work/projects/${projectId}/sections/${sectionId}/edit-diagram-text`, { edits })
}

export function saveDiagramSVG(projectId: string, sectionId: string, svg: string) {
  return api.post<import('../types/matcha-work').MWProject>(`/matcha-work/projects/${projectId}/sections/${sectionId}/save-diagram`, { svg })
}

export function createProjectChat(projectId: string, title?: string) {
  return api.post<import('../types/matcha-work').MWThread>(`/matcha-work/projects/${projectId}/chats`, { title })
}

// ── Collaborators ──

export function listCollaborators(projectId: string) {
  return api.get<import('../types/matcha-work').ProjectCollaborator[]>(`/matcha-work/projects/${projectId}/collaborators`)
}

export function addCollaborator(projectId: string, userId: string) {
  return api.post<import('../types/matcha-work').ProjectCollaborator[]>(`/matcha-work/projects/${projectId}/collaborators`, { user_id: userId })
}

export function removeCollaborator(projectId: string, userId: string) {
  return api.delete<import('../types/matcha-work').ProjectCollaborator[]>(`/matcha-work/projects/${projectId}/collaborators/${userId}`)
}

export function searchAdminUsers(query: string) {
  return api.get<{ user_id: string; name: string; email: string; avatar_url: string | null }[]>(
    `/matcha-work/admin-users/search?q=${encodeURIComponent(query)}`
  )
}

// ── Task Board ──

export interface ManualTask {
  id: string
  title: string
  description: string | null
  due_date: string | null
  date: string | null
  days_until: number | null
  horizon: string | null
  priority: string
  status: string
  completed_at: string | null
  link: string | null
  category: string
  source: 'manual'
  created_at: string
  updated_at: string
}

export interface TaskBoardResponse {
  auto_items: import('../types/dashboard').UpcomingItem[]
  manual_items: ManualTask[]
  dismissed_ids: string[]
  total: number
}

export function fetchTaskBoard() {
  return api.get<TaskBoardResponse>('/matcha-work/tasks')
}

export function createTask(body: { title: string; description?: string; due_date?: string; horizon?: string; priority?: string; link?: string }) {
  return api.post<ManualTask>('/matcha-work/tasks', body)
}

export function updateTask(id: string, body: Record<string, unknown>) {
  return api.patch<ManualTask>(`/matcha-work/tasks/${id}`, body)
}

export function deleteTask(id: string) {
  return api.delete(`/matcha-work/tasks/${id}`)
}

export function dismissAutoTask(source_category: string, source_id: string) {
  return api.post('/matcha-work/tasks/dismiss', { source_category, source_id })
}

export function exportProjectNew(projectId: string, format: 'pdf' | 'md' | 'docx') {
  return api.get<{ pdf_url?: string; docx_url?: string }>(`/matcha-work/projects/${projectId}/export/${format}`)
}

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
  return api.post<{ analyzed: number; candidates: import('../types/matcha-work').ResumeCandidate[] }>(
    `/matcha-work/projects/${projectId}/resume/analyze`
  )
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

export function updateProjectPosting(projectId: string, posting: Record<string, unknown>) {
  return api.put(`/matcha-work/projects/${projectId}/posting`, posting)
}

export function populatePostingFromChat(projectId: string, content: string) {
  return api.post<import('../types/matcha-work').MWProject>(
    `/matcha-work/projects/${projectId}/posting/from-chat`,
    { content }
  )
}

// ── Project (legacy thread-scoped) ──

export function initProject(threadId: string, title: string) {
  return api.post<{ current_state: Record<string, unknown>; version: number }>(
    `/matcha-work/threads/${threadId}/project/init`,
    { title }
  )
}

export function addProjectSection(threadId: string, section: { title?: string; content: string; source_message_id?: string }) {
  return api.post<{ section: { id: string }; current_state: Record<string, unknown>; version: number }>(
    `/matcha-work/threads/${threadId}/project/sections`,
    section
  )
}

export function updateProjectSection(threadId: string, sectionId: string, updates: { title?: string; content?: string }) {
  return api.put<{ current_state: Record<string, unknown>; version: number }>(
    `/matcha-work/threads/${threadId}/project/sections/${sectionId}`,
    updates
  )
}

export function deleteProjectSection(threadId: string, sectionId: string) {
  return api.delete<{ current_state: Record<string, unknown>; version: number }>(
    `/matcha-work/threads/${threadId}/project/sections/${sectionId}`
  )
}

export function reorderProjectSections(threadId: string, sectionIds: string[]) {
  return api.put<{ current_state: Record<string, unknown>; version: number }>(
    `/matcha-work/threads/${threadId}/project/sections/reorder`,
    { section_ids: sectionIds }
  )
}

export function exportProject(threadId: string, format: 'pdf' | 'md' | 'docx') {
  return api.get<{ pdf_url?: string; docx_url?: string }>(
    `/matcha-work/threads/${threadId}/project/export/${format}`
  )
}

export function uploadProjectImage(threadId: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return api.upload<{ url: string; filename: string }>(
    `/matcha-work/threads/${threadId}/project/images`,
    form
  )
}

// ── Project file attachments ──

export interface ProjectFile {
  id: string
  project_id: string
  filename: string
  storage_url: string
  content_type: string | null
  file_size: number
  created_at: string
}

export function listProjectFiles(projectId: string) {
  return api.get<ProjectFile[]>(`/matcha-work/projects/${projectId}/files`)
}

export function uploadProjectFile(projectId: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return api.upload<ProjectFile>(
    `/matcha-work/projects/${projectId}/files`,
    form,
  )
}

export function deleteProjectFile(projectId: string, fileId: string) {
  return api.delete(`/matcha-work/projects/${projectId}/files/${fileId}`)
}

// ── Research tasks ──

export function createResearchTask(projectId: string, body: { name: string; instructions: string }) {
  return api.post<ResearchTask>(`/matcha-work/projects/${projectId}/research-tasks`, body)
}

export function updateResearchTask(projectId: string, taskId: string, body: Partial<{ name: string; instructions: string }>) {
  return api.put<ResearchTask>(`/matcha-work/projects/${projectId}/research-tasks/${taskId}`, body)
}

export function deleteResearchTask(projectId: string, taskId: string) {
  return api.delete(`/matcha-work/projects/${projectId}/research-tasks/${taskId}`)
}

export function addResearchInputs(projectId: string, taskId: string, urls: string[]) {
  return api.post<{ added: number; inputs: ResearchInput[] }>(
    `/matcha-work/projects/${projectId}/research-tasks/${taskId}/inputs`, { urls },
  )
}

export function deleteResearchInput(projectId: string, taskId: string, inputId: string) {
  return api.delete(`/matcha-work/projects/${projectId}/research-tasks/${taskId}/inputs/${inputId}`)
}

export async function runResearchStream(
  projectId: string,
  taskId: string,
  onEvent: (event: { type: string; input_id?: string; message?: string; findings?: Record<string, unknown>; summary?: string; error?: string | null }) => void,
  signal?: AbortSignal,
  captureScreenshot?: boolean,
) {
  const token = localStorage.getItem('matcha_access_token')
  const qs = captureScreenshot ? '?capture_screenshot=true' : ''
  const res = await fetch(`${BASE}/matcha-work/projects/${projectId}/research-tasks/${taskId}/run${qs}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal,
  })
  if (!res.ok) throw new Error(`${res.status}`)
  const reader = res.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try { onEvent(JSON.parse(line.slice(6))) } catch {}
      }
    }
  }
}

export async function retryResearchStream(
  projectId: string,
  taskId: string,
  inputId: string,
  onEvent: (event: { type: string; input_id?: string; message?: string }) => void,
) {
  const token = localStorage.getItem('matcha_access_token')
  const res = await fetch(`${BASE}/matcha-work/projects/${projectId}/research-tasks/${taskId}/inputs/${inputId}/retry`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`${res.status}`)
  const reader = res.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try { onEvent(JSON.parse(line.slice(6))) } catch {}
      }
    }
  }
}

export async function followUpResearchStream(
  projectId: string,
  taskId: string,
  inputId: string,
  followUp: string,
  onEvent: (event: { type: string; input_id?: string; message?: string }) => void,
  signal?: AbortSignal,
  captureScreenshot?: boolean,
) {
  const token = localStorage.getItem('matcha_access_token')
  const qs = captureScreenshot ? '?capture_screenshot=true' : ''
  const res = await fetch(`${BASE}/matcha-work/projects/${projectId}/research-tasks/${taskId}/inputs/${inputId}/follow-up${qs}`, {
    method: 'POST',
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), 'Content-Type': 'application/json' },
    body: JSON.stringify({ follow_up: followUp }),
    signal,
  })
  if (!res.ok) throw new Error(`${res.status}`)
  const reader = res.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try { onEvent(JSON.parse(line.slice(6))) } catch {}
      }
    }
  }
}

// ── Project invites ──

export function inviteToProject(projectId: string, email: string) {
  return api.post<{ invited: boolean; email: string }>(`/matcha-work/projects/${projectId}/invite`, { email })
}

export function acceptProjectInvite(projectId: string) {
  return api.post(`/matcha-work/projects/${projectId}/invite/accept`)
}

export function declineProjectInvite(projectId: string) {
  return api.post(`/matcha-work/projects/${projectId}/invite/decline`)
}

export interface PendingInvite {
  project_id: string
  project_title: string
  invited_by: string
  invited_at: string
}

export function listPendingInvites() {
  return api.get<PendingInvite[]>('/matcha-work/project-invites')
}

export function stopResearch(projectId: string, taskId: string) {
  return api.post(`/matcha-work/projects/${projectId}/research-tasks/${taskId}/stop`)
}

// ── Candidate interviews ──

export async function sendCandidateInterviews(
  threadId: string,
  candidateIds: string[],
  positionTitle?: string,
  customMessage?: string,
) {
  return api.post<{
    sent: { id: string; name: string; email: string; interview_id: string; email_sent: boolean }[]
    failed: { id: string; error: string }[]
  }>(`/matcha-work/threads/${threadId}/resume/send-interviews`, {
    candidate_ids: candidateIds,
    position_title: positionTitle,
    custom_message: customMessage,
  })
}

export async function syncInterviewStatuses(threadId: string) {
  return api.post<{ updated: number }>(
    `/matcha-work/threads/${threadId}/resume/sync-interviews`
  )
}

// ── Inventory upload ──

export function uploadInventory(
  threadId: string,
  files: File[],
  callbacks: {
    onEvent: (event: MWStreamEvent) => void
    onComplete: (data: MWSendResponse) => void
    onError: (err: string) => void
  },
): AbortController {
  const ctrl = new AbortController()
  const timeout = setTimeout(() => ctrl.abort('timeout'), 300_000)

  ;(async () => {
    const token = await ensureFreshToken()
    const form = new FormData()
    files.forEach((f) => form.append('files', f))

    fetch(`${BASE}/matcha-work/threads/${threadId}/inventory/upload`, {
      method: 'POST',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
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
        if (!reader) {
          clearTimeout(timeout)
          callbacks.onError('No response body')
          return
        }

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
            if (raw === '[DONE]') {
              clearTimeout(timeout)
              return
            }

            try {
              const event: MWStreamEvent = JSON.parse(raw)
              callbacks.onEvent(event)
              if (event.type === 'complete') {
                clearTimeout(timeout)
                callbacks.onComplete(event.data)
                return
              }
              if (event.type === 'error') {
                clearTimeout(timeout)
                callbacks.onError(event.message)
                return
              }
            } catch {
              /* skip malformed */
            }
          }
        }
        clearTimeout(timeout)
      })
      .catch((e) => {
        clearTimeout(timeout)
        if (ctrl.signal.aborted) {
          if (ctrl.signal.reason === 'timeout') {
            callbacks.onError('Request timed out. Please try again.')
          }
        } else {
          callbacks.onError(e instanceof Error ? e.message : 'Upload failed')
        }
      })
  })()

  return ctrl
}

// ── SSE streaming ──

export function sendMessageStream(
  threadId: string,
  content: string,
  callbacks: {
    onEvent: (event: MWStreamEvent) => void
    onComplete: (data: MWSendResponse) => void
    onError: (err: string) => void
  },
  options?: { slide_index?: number; model?: string },
): AbortController {
  const ctrl = new AbortController()
  const timeout = setTimeout(() => ctrl.abort('timeout'), 90_000)

  ;(async () => {
    const token = await ensureFreshToken()

    fetch(`${BASE}/matcha-work/threads/${threadId}/messages/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ content, ...options }),
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
        if (!reader) {
          clearTimeout(timeout)
          callbacks.onError('No response body')
          return
        }

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
            if (raw === '[DONE]') {
              clearTimeout(timeout)
              return
            }

            try {
              const event: MWStreamEvent = JSON.parse(raw)
              callbacks.onEvent(event)
              if (event.type === 'complete') {
                clearTimeout(timeout)
                callbacks.onComplete(event.data)
                return
              }
              if (event.type === 'error') {
                clearTimeout(timeout)
                callbacks.onError(event.message)
                return
              }
            } catch {
              /* skip malformed */
            }
          }
        }
        clearTimeout(timeout)
      })
      .catch((e) => {
        clearTimeout(timeout)
        if (ctrl.signal.aborted) {
          if (ctrl.signal.reason === 'timeout') {
            callbacks.onError('Request timed out. Please try again.')
          }
          // else: user-initiated abort (navigated away), do nothing
        } else {
          callbacks.onError(e instanceof Error ? e.message : 'Stream failed')
        }
      })
  })()

  return ctrl
}


// ── Thread collaborators ──

export interface ThreadCollaborator {
  user_id: string
  name: string
  email: string
  avatar_url: string | null
  role: 'owner' | 'collaborator'
  created_at: string
}

export function listThreadCollaborators(threadId: string) {
  return api.get<ThreadCollaborator[]>(`/matcha-work/threads/${threadId}/collaborators`)
}

export function addThreadCollaborator(threadId: string, userId: string) {
  return api.post(`/matcha-work/threads/${threadId}/collaborators`, { user_id: userId })
}

export function removeThreadCollaborator(threadId: string, userId: string) {
  return api.delete(`/matcha-work/threads/${threadId}/collaborators/${userId}`)
}

export function searchThreadInvitableUsers(threadId: string, query: string) {
  return api.get<{ id: string; name: string; email: string; avatar_url: string | null }[]>(
    `/matcha-work/threads/${threadId}/collaborators/search?q=${encodeURIComponent(query)}`
  )
}

// ── Token Usage ──────────────────────────────────────────────────

export interface UsageSummary {
  period_days: number
  generated_at: string
  totals: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    operation_count: number
    estimated_operations: number
  }
  by_model: Array<{
    model: string
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    operation_count: number
  }>
}

export function fetchUsageSummary(periodDays = 30) {
  return api.get(`/matcha-work/usage/summary?period_days=${periodDays}`) as Promise<UsageSummary>
}

export function fetchUsageSummary24h() {
  return api.get('/matcha-work/usage/summary?period_days=1') as Promise<UsageSummary>
}

// ── Language Tutor Voice ──────────────────────────────────────────

export interface TutorStartResponse {
  interview_id: string
  websocket_url: string
  ws_auth_token: string
  max_session_duration_seconds: number
}

export interface TutorAnalysis {
  fluency_pace?: {
    overall_score: number
    speaking_speed: string
    pause_frequency: string
    filler_word_count: number
    filler_words_used: string[]
    flow_rating: string
    notes: string
  }
  vocabulary?: {
    overall_score: number
    variety_score: number
    appropriateness_score: number
    complexity_level: string
    notable_good_usage: string[]
    suggestions: string[]
  }
  grammar?: {
    overall_score: number
    sentence_structure_score: number
    tense_usage_score: number
    common_errors: Array<{ error: string; correction: string; explanation?: string }>
    notes: string
  }
  overall_proficiency?: {
    level: string
    level_description: string
    strengths: string[]
    areas_to_improve: string[]
  }
  practice_suggestions?: string[]
  session_summary?: string
  language?: string
}

export interface TutorStatusResponse {
  status: string
  tutor_analysis: TutorAnalysis | null
}

export function startTutorSession(threadId: string, language: 'en' | 'es', durationMinutes = 5) {
  return api.post<TutorStartResponse>(`/matcha-work/threads/${threadId}/tutor/start`, {
    language,
    duration_minutes: durationMinutes,
  })
}

export function getTutorStatus(threadId: string) {
  return api.get<TutorStatusResponse>(`/matcha-work/threads/${threadId}/tutor/status`)
}

export interface UtteranceError {
  error: string
  correction: string
  type: 'grammar' | 'vocabulary' | 'pronunciation'
  brief: string
}

export function checkUtterance(threadId: string, utterance: string, language: 'en' | 'es') {
  return api.post<{ errors: UtteranceError[] }>(`/matcha-work/threads/${threadId}/tutor/check`, {
    utterance,
    language,
  })
}
