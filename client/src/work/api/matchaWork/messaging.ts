import { api } from '../../../api/client'
import { postSSE, SSEHttpError } from '../../../api/sse'
import { reportApiError } from '../../../api/errorReporter'
import type { MWStreamEvent } from '../../types'
import { uploadFilesStream, type UploadStreamCallbacks } from './_base'

// ── Resume upload ──

export function uploadResumes(
  threadId: string,
  files: File[],
  callbacks: UploadStreamCallbacks,
): AbortController {
  return uploadFilesStream(`/matcha-work/threads/${threadId}/resume/upload`, files, callbacks)
}

// ── Inventory upload ──

export function uploadInventory(
  threadId: string,
  files: File[],
  callbacks: UploadStreamCallbacks,
): AbortController {
  return uploadFilesStream(`/matcha-work/threads/${threadId}/inventory/upload`, files, callbacks)
}

// ── SSE streaming ──

export function sendMessageStream(
  threadId: string,
  content: string,
  callbacks: UploadStreamCallbacks,
  options?: { slide_index?: number; model?: string },
): AbortController {
  const endpoint = `/matcha-work/threads/${threadId}/messages/stream`
  const ctrl = new AbortController()
  const timeout = setTimeout(() => ctrl.abort('timeout'), 180_000)

  // A turn is only "settled" once complete or error fires. Anything else that
  // ends the stream — [DONE] with no result, a drained reader, a proxy cutting
  // the connection — leaves the composer stuck on "Thinking…" with the input
  // disabled, so it must surface as an error rather than as silence.
  let settled = false

  void (async () => {
    try {
      await postSSE(
        endpoint,
        { content, ...options },
        (data) => {
          const event = data as MWStreamEvent
          callbacks.onEvent(event)
          if (event.type === 'complete') {
            settled = true
            callbacks.onComplete(event.data)
            return true
          }
          if (event.type === 'error') {
            settled = true
            reportApiError({ endpoint, status: 200, message: `SSE error event: ${event.message}` })
            callbacks.onError(event.message)
            return true
          }
        },
        { signal: ctrl.signal },
      )
      if (!settled && !ctrl.signal.aborted) {
        reportApiError({ endpoint, status: 200, message: 'SSE stream closed without complete/error event' })
        callbacks.onError('The response stream ended unexpectedly. Please try again.')
      }
    } catch (e) {
      if (ctrl.signal.aborted) {
        if (ctrl.signal.reason === 'timeout') {
          reportApiError({ endpoint, status: 0, message: 'SSE stream timed out after 180s' })
          callbacks.onError('Request timed out. Please try again.')
        }
        // else: user-initiated abort (navigated away), do nothing
        return
      }
      if (e instanceof SSEHttpError) {
        const msg = `${e.status}: ${e.message}`
        reportApiError({ endpoint, status: e.status, message: msg })
        callbacks.onError(msg)
        return
      }
      const msg = e instanceof Error ? e.message : 'Stream failed'
      reportApiError({ endpoint, status: 0, message: `SSE network/transport error: ${msg}` })
      callbacks.onError(msg)
    } finally {
      clearTimeout(timeout)
    }
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
