import { api, ensureFreshToken } from './client'
import type {
  MWThread,
  MWThreadDetail,
  MWCreateResponse,
  MWSendResponse,
  MWStreamEvent,
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

// ── Project ──

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
