import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MWSendResponse, MWThreadDetail } from '../../types'
import type { UploadStreamCallbacks } from '../../api/matchaWork/_base'
import { useThreadController } from './useThreadController'

const mock = vi.hoisted(() => ({
  threadId: 'thread-1', getThread: vi.fn(), send: vi.fn(), usage: vi.fn(),
}))
vi.mock('react-router-dom', () => ({ useParams: () => ({ threadId: mock.threadId }), useNavigate: () => vi.fn() }))
vi.mock('../../../hooks/useMe', () => ({ useMe: () => ({ me: null, hasFeature: () => false }) }))
vi.mock('../../../components/ui', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../../hooks/useModelPicker', () => ({ useModelPicker: () => ({ modelOptions: [], selectedModel: 'claude-haiku-5-5', setSelectedModel: vi.fn() }) }))
vi.mock('../../routes/WorkSurfaceContext', () => ({ useWorkBase: () => '/work' }))
vi.mock('./useThreadCollaboration', () => ({ useThreadCollaboration: () => ({ onlineUsers: [], typingUsers: new Map(), threadSocketRef: { current: null }, lastTypingSentRef: { current: 0 } }) }))
vi.mock('../../api/matchaWork', () => ({
  getThread: mock.getThread, sendMessageStream: mock.send,
  fetchUsageSummary: mock.usage, fetchUsageSummary24h: mock.usage,
  notifyUsageChanged: vi.fn(), notifyThreadsChanged: vi.fn(),
}))

const thread = { id: 'thread-1', title: 'Existing chat', messages: [], current_state: {}, version: 0 } as unknown as MWThreadDetail
let callbacks: UploadStreamCallbacks
let abort: AbortController

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('localStorage', { getItem: vi.fn(), setItem: vi.fn() })
  mock.threadId = 'thread-1'
  mock.getThread.mockResolvedValue(thread)
  mock.usage.mockResolvedValue(null)
  mock.send.mockImplementation((_id, _text, cb: UploadStreamCallbacks) => {
    callbacks = cb
    abort = new AbortController()
    return abort
  })
})

afterEach(() => vi.unstubAllGlobals())

async function start() {
  const hook = renderHook(() => useThreadController())
  await waitFor(() => expect(hook.result.current.loading).toBe(false))
  act(() => hook.result.current.handleSend('Hello'))
  return hook
}

describe('Claude reply stream', () => {
  it('accumulates deltas and replaces them with the authoritative completed message', async () => {
    const { result } = await start()
    act(() => {
      callbacks.onEvent({ type: 'delta', text: 'Hello ' })
      callbacks.onEvent({ type: 'delta', text: '🫖' })
    })
    expect(result.current.streamingText).toBe('Hello 🫖')
    const message = { id: 'assistant-1', role: 'assistant', content: 'Final validated reply' }
    act(() => callbacks.onComplete({ user_message: { id: 'user-1', role: 'user', content: 'Hello' }, assistant_message: message, current_state: {}, version: 1 } as MWSendResponse))
    expect(result.current.streamingText).toBe('')
    expect(result.current.streaming).toBe(false)
    expect(result.current.messages.at(-1)?.content).toBe('Final validated reply')
  })

  it('clears partial text on errors', async () => {
    const { result } = await start()
    act(() => callbacks.onEvent({ type: 'delta', text: 'Partial' }))
    act(() => callbacks.onError('Disconnected'))
    expect(result.current.streamingText).toBe('')
    expect(result.current.error).toBe('Disconnected')
    expect(result.current.streaming).toBe(false)
  })

  it('aborts and clears a stream when switching threads', async () => {
    const { result, rerender } = await start()
    act(() => callbacks.onEvent({ type: 'delta', text: 'Old reply' }))
    mock.threadId = 'thread-2'
    rerender()
    await waitFor(() => expect(result.current.streamingText).toBe(''))
    expect(abort.signal.aborted).toBe(true)
    expect(result.current.streaming).toBe(false)
  })
})
