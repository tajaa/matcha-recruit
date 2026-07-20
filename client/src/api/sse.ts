// Shared SSE consumption for every streaming endpoint in the app.
//
// api/client.ts can't stream (request() buffers the whole body and replays on
// 401), so streaming callers hand-rolled `fetch` + ReadableStream + a decode
// loop. Two frame families existed:
//
//   1. Pilot family  — `{type:'status'|'result'|'error'}` frames terminated by
//      `data: [DONE]`, split on '\n\n'. Five files, byte-identical loops.
//   2. Raw-event family — '\n'-split `data: ` lines with a per-file event
//      vocabulary (portal Ask HR, matcha-work, admin studio, ER panels, …).
//
// Splitting on '\n' and keeping `data: ` lines subsumes both: a '\n\n'-delimited
// SSE event carries exactly one `data:` line, so the pilot family parses
// identically under the line-oriented rule.
//
// Streams can't replay a mid-flight 401 refresh-and-retry — a half-consumed
// body is gone — so auth goes through authStreamHeaders(), which refreshes
// proactively before the request opens.

import { authStreamHeaders } from './client'

const BASE = import.meta.env.VITE_API_URL || '/api'

// ---------------------------------------------------------------------------
// Shared pilot types (E1) — these were redeclared verbatim across the five
// pilot api modules. PilotSession is deliberately NOT here: its shape really
// does differ per pilot (company_id vs broker_id, per-pilot counters).
// ---------------------------------------------------------------------------

export type SessionStatus = 'active' | 'closed'

/** A persisted transcript turn. `metadata` is per-pilot, hence the parameter. */
export type PilotMessage<TMeta = unknown> = {
  role: 'user' | 'assistant' | 'system'
  content: string
  metadata: TMeta
  created_at: string
}

/** The status/result/error callback triple every pilot console passes down. */
export type ChatHandlers<TResult> = {
  onStatus?: (message: string) => void
  onResult?: (data: TResult) => void
  onError?: (message: string) => void
}

// ---------------------------------------------------------------------------
// Core parser
// ---------------------------------------------------------------------------

/** Return `true` from a frame handler to stop consuming and cancel the reader. */
export type FrameHandler = (data: unknown) => boolean | void

/**
 * Drain an SSE response body, invoking `onFrame` per decoded JSON frame.
 *
 * Buffers across chunk boundaries — a frame split by the network is reassembled
 * rather than dropped. Malformed/partial JSON is skipped, not thrown: one bad
 * frame shouldn't kill a turn. Returns when the stream ends, when a `[DONE]`
 * sentinel arrives, or when `onFrame` returns true.
 */
export async function consumeSSE(res: Response, onFrame: FrameHandler): Promise<void> {
  if (!res.body) return
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  /** Feed one complete line. Returns true if the caller should stop consuming. */
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
      return false // partial or non-JSON frame
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
      // Keep the trailing partial line for the next chunk.
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (flush(line)) return
      }
    }
    // The stream ended. Anything still buffered is a final line the server sent
    // without a trailing newline — dropping it loses a real frame, and when that
    // frame is the terminal `complete` the caller waits forever for a result
    // that already arrived. decoder.decode() with no argument flushes any
    // pending multi-byte sequence at the same time.
    const tail = (buf + decoder.decode()).trim()
    if (tail) flush(tail)
  } finally {
    // Releases the lock whether we finished, early-returned or threw. Without
    // this an early return leaves the body locked and un-collectable.
    reader.cancel().catch(() => {})
  }
}

export type PostSSEOptions = {
  signal?: AbortSignal
  /** Attach the bearer token (proactively refreshed). Default true. */
  auth?: boolean
  headers?: Record<string, string>
  method?: string
}

/** Non-ok response from postSSE, carrying the parsed body for callers that
 *  need it (e.g. the broker document gate's 409 payload). */
export class SSEHttpError extends Error {
  status: number
  body: unknown
  constructor(message: string, status: number, body: unknown) {
    super(message)
    this.name = 'SSEHttpError'
    this.status = status
    this.body = body
  }
}

async function _readDetail(res: Response): Promise<{ detail: string; body: unknown }> {
  try {
    const body = await res.json()
    const detail = typeof body?.detail === 'string' ? body.detail : ''
    return { detail, body }
  } catch {
    return { detail: '', body: null } // non-JSON error body
  }
}

/**
 * POST and stream the SSE response.
 *
 * `body` is sent as JSON, or passed through untouched when it's FormData (the
 * browser must set the multipart boundary itself, so Content-Type is omitted).
 * On a non-ok response throws SSEHttpError with the backend's `detail` as the
 * message where one is present.
 */
export async function postSSE(
  path: string,
  body: unknown,
  onFrame: FrameHandler,
  opts: PostSSEOptions = {},
): Promise<void> {
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData
  const base = opts.auth === false
    ? {}
    : await authStreamHeaders(isForm ? undefined : { 'Content-Type': 'application/json' })
  const headers: Record<string, string> = {
    ...base,
    ...(opts.auth === false && !isForm ? { 'Content-Type': 'application/json' } : {}),
    ...opts.headers,
  }

  const res = await fetch(`${BASE}${path}`, {
    method: opts.method ?? 'POST',
    headers,
    body: isForm ? (body as FormData) : body === undefined ? undefined : JSON.stringify(body),
    signal: opts.signal,
  })

  if (!res.ok) {
    const { detail, body: parsed } = await _readDetail(res)
    throw new SSEHttpError(detail || `Request failed (${res.status})`, res.status, parsed)
  }
  // A 2xx with no body is an EMPTY stream, not a failure — throwing here would
  // surface a nonsensical "Request failed (200)". consumeSSE no-ops on it.
  await consumeSSE(res, onFrame)
}

// ---------------------------------------------------------------------------
// Pilot turn
// ---------------------------------------------------------------------------

export type PilotChatOptions = {
  signal?: AbortSignal
  /**
   * Inspect a non-ok response before the default onError fires. Return true to
   * claim the error (suppressing onError) — the broker document gate uses this
   * for its 409 `missing_required_documents` payload.
   */
  onHttpError?: (err: SSEHttpError) => boolean | void
}

/**
 * One grounded pilot turn: `{type:'status'|'result'|'error'}` frames.
 *
 * An aborted turn resolves quietly rather than surfacing an error — switching
 * sessions mid-stream is a normal interaction, not a failure.
 */
export async function streamPilotChat<TResult>(
  path: string,
  body: unknown,
  h: ChatHandlers<TResult>,
  opts: PilotChatOptions = {},
): Promise<void> {
  try {
    await postSSE(
      path,
      body,
      (data) => {
        const frame = data as { type?: string; message?: string; data?: TResult }
        if (frame.type === 'status') h.onStatus?.(frame.message ?? '')
        else if (frame.type === 'result') h.onResult?.(frame.data as TResult)
        else if (frame.type === 'error') h.onError?.(frame.message ?? 'Chat failed')
      },
      { signal: opts.signal },
    )
  } catch (e) {
    if (opts.signal?.aborted) return
    if (e instanceof SSEHttpError) {
      if (opts.onHttpError?.(e) === true) return
      h.onError?.(e.message)
      return
    }
    h.onError?.('Chat connection dropped — please try again.')
  }
}
