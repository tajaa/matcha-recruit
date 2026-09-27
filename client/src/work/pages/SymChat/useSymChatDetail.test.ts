import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SymChatDetail } from '../../api/matchaWork/symChat'
import { SYM_CHAT_POLL_MS, useSymChatDetail } from './useSymChatDetail'

const api = vi.hoisted(() => ({
  getSymChat: vi.fn(),
  sendSymChatMessage: vi.fn(),
  cancelSymChat: vi.fn(),
}))
const socket = vi.hoisted(() => {
  const listeners = new Set<(e: { sym_chat_id: string }) => void>()
  return {
    listeners,
    addSymChatListener: vi.fn((fn: (e: { sym_chat_id: string }) => void) => listeners.add(fn)),
    removeSymChatListener: vi.fn((fn: (e: { sym_chat_id: string }) => void) => listeners.delete(fn)),
    emit: (e: { sym_chat_id: string }) => listeners.forEach((fn) => fn(e)),
  }
})

vi.mock('../../api/matchaWork/symChat', () => api)
vi.mock('../../api/channelSocket', () => ({ getSharedChannelSocket: () => socket }))

function detail(overrides: Partial<SymChatDetail> = {}): SymChatDetail {
  return {
    id: 'chat-1', kind: 'decide', title: 'Lunch', objective: '', config: { options: [] },
    status: 'open', shape: {}, resolution: null, resolved_at: null, is_organizer: true, created_at: null,
    participants: [], updates: [], messages: [], my_stance: null,
    ...overrides,
  }
}

beforeEach(() => {
  api.getSymChat.mockReset().mockResolvedValue(detail())
  api.sendSymChatMessage.mockReset()
  api.cancelSymChat.mockReset()
  socket.listeners.clear()
})

afterEach(() => vi.useRealTimers())

describe('useSymChatDetail', () => {
  it('loads, then refetches on a WS nudge for this chat only', async () => {
    const { result, unmount } = renderHook(() => useSymChatDetail('chat-1'))
    await waitFor(() => expect(result.current.detail?.id).toBe('chat-1'))
    expect(api.getSymChat).toHaveBeenCalledTimes(1)

    act(() => socket.emit({ sym_chat_id: 'other' }))
    expect(api.getSymChat).toHaveBeenCalledTimes(1)

    api.getSymChat.mockResolvedValue(detail({ status: 'resolved' }))
    act(() => socket.emit({ sym_chat_id: 'chat-1' }))
    await waitFor(() => expect(result.current.detail?.status).toBe('resolved'))

    unmount()
    expect(socket.listeners.size).toBe(0)
  })

  it('polls while open and stops once the chat closes', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const { result } = renderHook(() => useSymChatDetail('chat-1'))
    await waitFor(() => expect(result.current.detail).not.toBeNull())

    await act(async () => { await vi.advanceTimersByTimeAsync(SYM_CHAT_POLL_MS) })
    expect(api.getSymChat).toHaveBeenCalledTimes(2)

    api.getSymChat.mockResolvedValue(detail({ status: 'cancelled' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(SYM_CHAT_POLL_MS) })
    await waitFor(() => expect(result.current.detail?.status).toBe('cancelled'))
    const calls = api.getSymChat.mock.calls.length
    await act(async () => { await vi.advanceTimersByTimeAsync(SYM_CHAT_POLL_MS * 2) })
    expect(api.getSymChat).toHaveBeenCalledTimes(calls)
  })

  it('shows my message optimistically, then reconciles with the server', async () => {
    const { result } = renderHook(() => useSymChatDetail('chat-1'))
    await waitFor(() => expect(result.current.detail).not.toBeNull())

    let resolveSend: (v: unknown) => void = () => {}
    api.sendSymChatMessage.mockReturnValue(new Promise((r) => { resolveSend = r }))
    let sent: Promise<boolean> = Promise.resolve(false)
    act(() => { sent = result.current.send('Thai is fine') })
    expect(result.current.detail?.messages.map((m) => m.content)).toEqual(['Thai is fine'])
    expect(result.current.sending).toBe(true)

    api.getSymChat.mockResolvedValue(detail({
      messages: [
        { id: 'm1', role: 'user', content: 'Thai is fine', created_at: null },
        { id: 'm2', role: 'assistant', content: 'Noted.', created_at: null },
      ],
    }))
    await act(async () => { resolveSend({}); await sent })
    expect(api.sendSymChatMessage).toHaveBeenCalledWith('chat-1', 'Thai is fine')
    expect(result.current.detail?.messages.map((m) => m.id)).toEqual(['m1', 'm2'])
  })

  it('reports a failed send and returns false so the draft can be restored', async () => {
    const { result } = renderHook(() => useSymChatDetail('chat-1'))
    await waitFor(() => expect(result.current.detail).not.toBeNull())
    api.sendSymChatMessage.mockRejectedValue(new Error('This sym-chat is resolved'))
    let ok = true
    await act(async () => { ok = await result.current.send('hello') })
    expect(ok).toBe(false)
    expect(result.current.sendError).toBe('This sym-chat is resolved')
  })
})
