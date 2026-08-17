import { describe, expect, it, beforeEach, vi } from 'vitest'
import type { MWSendResponse, MWStreamEvent } from '../../types'
import { sendMessageStream } from './messaging'
import { postSSE } from '../../../api/sse'
import { reportApiError } from '../../../api/errorReporter'

vi.mock('../../../api/sse', () => ({
  postSSE: vi.fn(),
  SSEHttpError: class SSEHttpError extends Error {},
}))

vi.mock('../../../api/errorReporter', () => ({
  reportApiError: vi.fn(),
}))

const postSSEMock = vi.mocked(postSSE)
const reportApiErrorMock = vi.mocked(reportApiError)

const completeData = {} as MWSendResponse

async function flushStream() {
  await new Promise<void>((resolve) => setTimeout(resolve, 0))
}

describe('sendMessageStream', () => {
  let events: MWStreamEvent[]

  beforeEach(() => {
    events = []
    vi.clearAllMocks()
    postSSEMock.mockImplementation(async (_path, _body, onFrame) => {
      for (const event of events) {
        if (onFrame(event) === true) break
      }
    })
  })

  it('keeps consuming after a Huume error so a later complete frame wins', async () => {
    events = [
      { type: 'error', message: 'Huume hit a problem mid-turn — keeping what worked.' },
      { type: 'complete', data: completeData },
    ]
    const callbacks = {
      onEvent: vi.fn(),
      onComplete: vi.fn(),
      onError: vi.fn(),
    }

    sendMessageStream('thread-1', 'build the plan', callbacks)
    await flushStream()

    expect(callbacks.onComplete).toHaveBeenCalledWith(completeData)
    expect(callbacks.onError).not.toHaveBeenCalled()
    expect(reportApiErrorMock).not.toHaveBeenCalled()
  })

  it('surfaces an SSE error when no complete frame follows', async () => {
    const message = 'Huume is being used a lot right now — try again in a bit.'
    events = [{ type: 'error', message }]
    const callbacks = {
      onEvent: vi.fn(),
      onComplete: vi.fn(),
      onError: vi.fn(),
    }

    sendMessageStream('thread-1', 'try again', callbacks)
    await flushStream()

    expect(callbacks.onComplete).not.toHaveBeenCalled()
    expect(callbacks.onError).toHaveBeenCalledWith(message)
    expect(reportApiErrorMock).toHaveBeenCalledWith({
      endpoint: '/matcha-work/threads/thread-1/messages/stream',
      status: 200,
      message: `SSE error event: ${message}`,
    })
  })

  it('reports an unexpected stream end when no terminal frame arrives', async () => {
    const callbacks = {
      onEvent: vi.fn(),
      onComplete: vi.fn(),
      onError: vi.fn(),
    }

    sendMessageStream('thread-1', 'hello', callbacks)
    await flushStream()

    expect(callbacks.onError).toHaveBeenCalledWith('The response stream ended unexpectedly. Please try again.')
    expect(reportApiErrorMock).toHaveBeenCalledWith({
      endpoint: '/matcha-work/threads/thread-1/messages/stream',
      status: 200,
      message: 'SSE stream closed without complete/error event',
    })
  })
})
