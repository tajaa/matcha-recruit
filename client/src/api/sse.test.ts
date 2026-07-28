import { describe, it, expect, vi } from 'vitest'
import { consumeSSE, SSEHttpError } from './sse'
import { ApiError } from './client'

/** Build a Response whose body streams the given string chunks verbatim, so a
 *  test can place a frame boundary exactly where it wants one. */
function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c))
      controller.close()
    },
  })
  return new Response(body, { status: 200 })
}

const frames = async (chunks: string[]) => {
  const seen: unknown[] = []
  await consumeSSE(sseResponse(chunks), (d) => { seen.push(d) })
  return seen
}

describe('consumeSSE', () => {
  it('parses newline-delimited data frames', async () => {
    expect(await frames(['data: {"a":1}\ndata: {"a":2}\n'])).toEqual([{ a: 1 }, { a: 2 }])
  })

  it('parses the pilot family\'s blank-line-separated frames identically', async () => {
    expect(await frames(['data: {"type":"status"}\n\ndata: {"type":"result"}\n\n']))
      .toEqual([{ type: 'status' }, { type: 'result' }])
  })

  it('reassembles a frame split across chunk boundaries', async () => {
    expect(await frames(['data: {"a"', ':1}\n'])).toEqual([{ a: 1 }])
  })

  // The regression this file exists for: a server that ends without a trailing
  // newline. Dropping the buffered tail loses a real frame — and when that frame
  // is the terminal `complete`, the caller waits forever for a result it was sent.
  it('emits a final frame sent without a trailing newline', async () => {
    expect(await frames(['data: {"type":"complete"}'])).toEqual([{ type: 'complete' }])
  })

  it('emits a final unterminated frame that also straddles a chunk boundary', async () => {
    expect(await frames(['data: {"type":"comp', 'lete"}'])).toEqual([{ type: 'complete' }])
  })

  it('stops at [DONE] and ignores anything after it', async () => {
    expect(await frames(['data: {"a":1}\ndata: [DONE]\ndata: {"a":2}\n'])).toEqual([{ a: 1 }])
  })

  it('treats an unterminated [DONE] as terminal, not as a frame', async () => {
    expect(await frames(['data: {"a":1}\ndata: [DONE]'])).toEqual([{ a: 1 }])
  })

  it('handles CRLF line endings', async () => {
    expect(await frames(['data: {"a":1}\r\ndata: {"a":2}\r\n'])).toEqual([{ a: 1 }, { a: 2 }])
  })

  it('skips malformed frames without killing the stream', async () => {
    expect(await frames(['data: {oops\ndata: {"a":1}\n'])).toEqual([{ a: 1 }])
  })

  it('skips comment/keepalive lines and non-data lines', async () => {
    expect(await frames([': keepalive\nevent: ping\ndata: {"a":1}\n'])).toEqual([{ a: 1 }])
  })

  it('decodes a multi-byte character split across chunks', async () => {
    const encoder = new TextEncoder()
    const full = encoder.encode('data: {"s":"€"}\n')
    // Slice mid-euro (3 bytes): without { stream: true } this yields U+FFFD.
    const cut = 12
    const seen: unknown[] = []
    const body = new ReadableStream<Uint8Array>({
      start(c) { c.enqueue(full.slice(0, cut)); c.enqueue(full.slice(cut)); c.close() },
    })
    await consumeSSE(new Response(body, { status: 200 }), (d) => { seen.push(d) })
    expect(seen).toEqual([{ s: '€' }])
  })

  it('stops consuming when the handler returns true', async () => {
    const onFrame = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true)
    await consumeSSE(sseResponse(['data: {"a":1}\ndata: {"a":2}\ndata: {"a":3}\n']), onFrame)
    expect(onFrame).toHaveBeenCalledTimes(2)
  })

  it('no-ops on a response with no body rather than throwing', async () => {
    await expect(consumeSSE(new Response(null, { status: 200 }), () => {})).resolves.toBeUndefined()
  })
})

describe('SSEHttpError', () => {
  it('is an ApiError — one instanceof covers both transports', () => {
    const e = new SSEHttpError('conflict', 409, { detail: 'conflict' })
    expect(e).toBeInstanceOf(SSEHttpError)
    expect(e).toBeInstanceOf(ApiError)
    expect(e).toBeInstanceOf(Error)
  })

  // Guards the useDefineForClassFields hazard: a redeclared field in the
  // subclass would clobber the parent-assigned status/body to undefined.
  it('carries status/body/message through super', () => {
    const e = new SSEHttpError('conflict', 409, { detail: 'conflict' })
    expect(e.status).toBe(409)
    expect(e.body).toEqual({ detail: 'conflict' })
    expect(e.message).toBe('conflict')
    expect(e.name).toBe('SSEHttpError')
  })

  it('a plain ApiError is NOT an SSEHttpError', () => {
    expect(new ApiError('x', 500, null)).not.toBeInstanceOf(SSEHttpError)
  })
})
