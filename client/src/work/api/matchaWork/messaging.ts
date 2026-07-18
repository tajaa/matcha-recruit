import { api, ensureFreshToken } from '../../../api/client'
import { reportApiError, reportJsError } from '../../../api/errorReporter'
import type { MWSendResponse, MWStreamEvent } from '../../types'
import { BASE } from './_base'

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
  const timeout = setTimeout(() => ctrl.abort('timeout'), 180_000)

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
          const msg = `${res.status}: ${text}`
          reportApiError({
            endpoint: `/matcha-work/threads/${threadId}/messages/stream`,
            status: res.status,
            message: msg,
            body: { text: text.slice(0, 500) },
          })
          callbacks.onError(msg)
          return
        }

        const reader = res.body?.getReader()
        if (!reader) {
          clearTimeout(timeout)
          reportApiError({
            endpoint: `/matcha-work/threads/${threadId}/messages/stream`,
            status: 0,
            message: 'No response body on SSE stream',
          })
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
              // Stream closed without a complete/error event — if we got here,
              // neither callback fired. Leaving the caller waiting freezes the
              // composer until a full page reload.
              clearTimeout(timeout)
              reportApiError({
                endpoint: `/matcha-work/threads/${threadId}/messages/stream`,
                status: 200,
                message: 'SSE stream ended ([DONE]) without complete/error event',
              })
              callbacks.onError('The response stream ended unexpectedly. Please try again.')
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
                reportApiError({
                  endpoint: `/matcha-work/threads/${threadId}/messages/stream`,
                  status: 200,
                  message: `SSE error event: ${event.message}`,
                })
                callbacks.onError(event.message)
                return
              }
            } catch (parseErr) {
              reportJsError(parseErr, {
                source: 'sendMessageStream SSE parse',
                raw: raw.slice(0, 300),
              })
            }
          }
        }
        // Reader drained without a complete/error event (proxy cut the
        // connection, backend crashed mid-stream, …). Surface it — silence
        // here left the UI stuck on "Thinking…" with the input disabled.
        clearTimeout(timeout)
        if (!ctrl.signal.aborted) {
          reportApiError({
            endpoint: `/matcha-work/threads/${threadId}/messages/stream`,
            status: 200,
            message: 'SSE stream closed without complete/error event',
          })
          callbacks.onError('The response stream ended unexpectedly. Please try again.')
        }
      })
      .catch((e) => {
        clearTimeout(timeout)
        if (ctrl.signal.aborted) {
          if (ctrl.signal.reason === 'timeout') {
            reportApiError({
              endpoint: `/matcha-work/threads/${threadId}/messages/stream`,
              status: 0,
              message: 'SSE stream timed out after 180s',
            })
            callbacks.onError('Request timed out. Please try again.')
          }
          // else: user-initiated abort (navigated away), do nothing
        } else {
          const msg = e instanceof Error ? e.message : 'Stream failed'
          reportApiError({
            endpoint: `/matcha-work/threads/${threadId}/messages/stream`,
            status: 0,
            message: `SSE network/transport error: ${msg}`,
          })
          callbacks.onError(msg)
        }
      })
  })()

  return ctrl
}

// ── Candidate interviews (thread-scoped) ──

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
