// Shared base URL for matcha-work streaming (SSE) calls that use raw `fetch`
// instead of the `api` helper, plus the multipart upload-stream driver the
// resume / inventory / candidate uploads share. Internal to this package.

import { postSSE, SSEHttpError } from '../../../api/sse'
import type { MWSendResponse, MWStreamEvent } from '../../types'

export const BASE = import.meta.env.VITE_API_URL ?? '/api'

/** Uploads share a 5-minute ceiling — a large resume batch is slow, but a
 *  stream still quiet past this is hung, not working. */
const UPLOAD_TIMEOUT_MS = 300_000

export type UploadStreamCallbacks = {
  onEvent: (event: MWStreamEvent) => void
  onComplete: (data: MWSendResponse) => void
  onError: (err: string) => void
}

/**
 * POST files as multipart and drive the SSE progress stream.
 *
 * Returns the AbortController so the caller can cancel. The timeout aborts with
 * reason 'timeout', so a hang reports differently from a user cancel (which is
 * silent). The stream ends on `complete`, on `error`, or on the `[DONE]`
 * sentinel — whichever the backend sends first.
 */
export function uploadFilesStream(
  path: string,
  files: File[],
  callbacks: UploadStreamCallbacks,
): AbortController {
  const ctrl = new AbortController()
  const timeout = setTimeout(() => ctrl.abort('timeout'), UPLOAD_TIMEOUT_MS)

  const form = new FormData()
  files.forEach((f) => form.append('files', f))

  void (async () => {
    try {
      await postSSE(
        path,
        form,
        (data) => {
          const event = data as MWStreamEvent
          callbacks.onEvent(event)
          if (event.type === 'complete') {
            callbacks.onComplete(event.data)
            return true // stop consuming
          }
          if (event.type === 'error') {
            callbacks.onError(event.message)
            return true
          }
        },
        { signal: ctrl.signal },
      )
    } catch (e) {
      if (ctrl.signal.aborted) {
        // A user cancel is silent; only a timeout is worth reporting.
        if (ctrl.signal.reason === 'timeout') callbacks.onError('Request timed out. Please try again.')
        return
      }
      if (e instanceof SSEHttpError) callbacks.onError(`${e.status}: ${e.message}`)
      else callbacks.onError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      clearTimeout(timeout)
    }
  })()

  return ctrl
}
