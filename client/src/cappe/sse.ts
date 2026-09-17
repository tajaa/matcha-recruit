// SSE consumption for Cappe's streaming endpoints (today: Merlin's agent turn).
//
// This is a deliberate parallel of `api/sse.ts` rather than an import of it.
// That module authenticates through `authStreamHeaders`, which reads matcha's
// `matcha_access_token` — a Cappe session has its own `cappe_*` token pair and
// its own /api/cappe base, and the two must not cross (see client/CLAUDE.md's
// boundary rules and api.ts's header comment). The parser below is the same
// line-oriented one; only auth and base differ.
//
// `cappeApi.request()` can't stream: it buffers the whole body so it can replay
// on a 401. A stream can't replay — hence `cappeStreamHeaders`, which refreshes
// the token BEFORE the request opens.

import {
  CAPPE_NETWORK_ERROR, cappeApiBase, cappeLogout, cappeStreamHeaders,
  getCappeToken, refreshCappeSession,
} from './api'

/** Return `true` from a frame handler to stop consuming and cancel the reader. */
export type CappeFrameHandler = (data: unknown) => boolean | void

/**
 * Drain an SSE response body, invoking `onFrame` per decoded JSON frame.
 *
 * Buffers across chunk boundaries — a frame split by the network is reassembled
 * rather than dropped. Malformed JSON is skipped, not thrown: one bad frame
 * shouldn't kill a turn. Returns when the stream ends, on a `[DONE]` sentinel,
 * or when `onFrame` returns true.
 */
export async function consumeCappeSSE(res: Response, onFrame: CappeFrameHandler): Promise<void> {
  if (!res.body) return
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  const flush = (line: string): boolean => {
    if (!line.startsWith('data: ')) return false
    // .trim() also strips the '\r' of a CRLF stream — SSE permits either ending.
    const payload = line.slice(6).trim()
    if (!payload) return false
    if (payload === '[DONE]') return true
    let data: unknown
    try {
      data = JSON.parse(payload)
    } catch {
      return false
    }
    return onFrame(data) === true
  }

  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      // { stream: true } is load-bearing: without it a multi-byte character
      // straddling a chunk boundary decodes to a replacement char.
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (flush(line)) return
      }
    }
    // A final line the server sent without a trailing newline is a real frame —
    // and when it's the terminal `result`, dropping it means waiting forever for
    // something that already arrived.
    const tail = (buf + decoder.decode()).trim()
    if (tail) flush(tail)
  } finally {
    // Releases the lock whether we finished, early-returned or threw.
    reader.cancel().catch(() => {})
  }
}

export class CappeSSEHttpError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'CappeSSEHttpError'
    this.status = status
  }
}

/** POST and stream the SSE response. Throws CappeSSEHttpError on a non-ok
 *  response, using the backend's `detail` as the message where present.
 *
 *  A 401 here is recoverable exactly once: `cappeStreamHeaders` only refreshes
 *  a token that is already within 60s of expiry, so a token revoked or aged
 *  out by a clock skew still opens the stream and comes back 401. Previously
 *  that surfaced as a bare "Request failed (401)" in the middle of a Merlin
 *  turn with a live session sitting behind it. Refresh once, reopen, and only
 *  then treat it as a dead session. */
export async function postCappeSSE(
  path: string,
  body: unknown,
  onFrame: CappeFrameHandler,
  opts: { signal?: AbortSignal } = {},
): Promise<void> {
  const payload = JSON.stringify(body ?? {})
  const open = (token: string | null) => fetch(`${cappeApiBase}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: payload,
    signal: opts.signal,
  })

  const headers = await cappeStreamHeaders({ 'Content-Type': 'application/json' })
  let res = await fetch(`${cappeApiBase}${path}`, {
    method: 'POST',
    headers,
    body: payload,
    signal: opts.signal,
  })

  if (res.status === 401) {
    // Release the rejected response's body before opening a second stream.
    await res.body?.cancel().catch(() => {})
    const outcome = await refreshCappeSession()
    if (outcome === 'dead') {
      cappeLogout()
      throw new CappeSSEHttpError('Session expired', 401)
    }
    if (outcome === 'transport') {
      // Never end the session on a network blip — this runs mid-edit.
      throw new CappeSSEHttpError(CAPPE_NETWORK_ERROR, 401)
    }
    res = await open(getCappeToken())
    if (res.status === 401) {
      await res.body?.cancel().catch(() => {})
      cappeLogout()
      throw new CappeSSEHttpError('Session expired', 401)
    }
  }

  if (!res.ok) {
    let detail = ''
    try {
      const parsed = await res.json()
      if (typeof parsed?.detail === 'string') detail = parsed.detail
    } catch { /* non-JSON error body */ }
    throw new CappeSSEHttpError(detail || `Request failed (${res.status})`, res.status)
  }
  await consumeCappeSSE(res, onFrame)
}
