import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useMerlin } from './useMerlin'

type StreamCall = {
  onFrame: (frame: unknown) => void
  signal?: AbortSignal
  resolve: () => void
  reject: (error: unknown) => void
}

const mocks = vi.hoisted(() => ({
  streamCalls: [] as StreamCall[],
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
  upload: vi.fn(),
}))

const storage = (() => {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, String(value)) },
    removeItem: (key: string) => { values.delete(key) },
    clear: () => { values.clear() },
    key: (index: number) => [...values.keys()][index] ?? null,
    get length() { return values.size },
  }
})()

vi.mock('../../../api', () => ({
  cappeApi: {
    get: mocks.get,
    patch: mocks.patch,
    post: mocks.post,
    upload: mocks.upload,
    delete: vi.fn(),
  },
}))

vi.mock('../../../sse', () => ({
  postCappeSSE: vi.fn((
    _path: string,
    _body: unknown,
    onFrame: (frame: unknown) => void,
    options?: { signal?: AbortSignal },
  ) => new Promise<void>((resolve, reject) => {
    mocks.streamCalls.push({ onFrame, signal: options?.signal, resolve, reject })
  })),
}))

beforeEach(() => {
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage })
  localStorage.clear()
  mocks.streamCalls.length = 0
  mocks.get.mockReset().mockResolvedValue([])
  mocks.patch.mockReset().mockResolvedValue(undefined)
  mocks.post.mockReset()
  mocks.upload.mockReset()
})

describe('useMerlin turn ownership', () => {
  it('does not let an aborted page turn clear a newer turn state', async () => {
    const { result, rerender } = renderHook(
      ({ pageId }) => useMerlin(
        'site-1',
        pageId,
        () => ({ blocks: [], theme: {} }),
        vi.fn(),
      ),
      { initialProps: { pageId: 'page-a' } },
    )

    let first!: Promise<void>
    act(() => { first = result.current.send('first turn') })
    await waitFor(() => expect(mocks.streamCalls).toHaveLength(1))
    expect(result.current.sending).toBe(true)

    rerender({ pageId: 'page-b' })
    await waitFor(() => expect(result.current.sending).toBe(false))
    expect(mocks.streamCalls[0].signal?.aborted).toBe(true)

    let second!: Promise<void>
    act(() => { second = result.current.send('second turn') })
    await waitFor(() => expect(mocks.streamCalls).toHaveLength(2))
    act(() => {
      mocks.streamCalls[1].onFrame({ type: 'status', message: 'Building page B' })
      mocks.streamCalls[1].onFrame({ type: 'step', kind: 'inspect', label: 'Inspecting page B' })
    })
    expect(result.current.sending).toBe(true)
    expect(result.current.status).toBe('Building page B')
    expect(result.current.liveSteps).toHaveLength(1)

    await act(async () => {
      mocks.streamCalls[0].reject(new DOMException('Aborted', 'AbortError'))
      await first
    })

    expect(result.current.sending).toBe(true)
    expect(result.current.status).toBe('Building page B')
    expect(result.current.liveSteps).toHaveLength(1)

    await act(async () => {
      mocks.streamCalls[1].onFrame({
        type: 'result',
        data: { message: 'Done', ops: [], rejected: [], tier: 'lite' },
      })
      mocks.streamCalls[1].resolve()
      await second
    })
    expect(result.current.sending).toBe(false)
  })
})
