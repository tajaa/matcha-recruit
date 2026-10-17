import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/client'
import { useRecap } from './useRecap'
import type { RecapDetail } from '../types'

const mock = vi.hoisted(() => ({ get: vi.fn(), owner: 'owner-a' }))
vi.mock('../api/matchaWork/recaps', () => ({ getRecap: mock.get }))
vi.mock('../../hooks/useMe', () => ({ useMe: () => ({ me: { user: { id: mock.owner } }, isPersonal: true }) }))
const detail = (state = 'queued') => ({ id: 'recap', title: 'Private recap', state }) as RecapDetail
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (error: Error) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
beforeEach(() => { vi.clearAllMocks(); mock.owner = 'owner-a'; Object.defineProperty(document, 'hidden', { configurable: true, value: false }) })
afterEach(() => { vi.useRealTimers() })
describe('recap polling', () => {
  it('retries a temporary read failure', async () => {
    vi.useFakeTimers()
    mock.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValue(detail('ready'))
    const { result } = renderHook(() => useRecap('recap', 0))
    await act(async () => { await Promise.resolve() })
    expect(result.current.error).toContain('Retrying')
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000) })
    expect(result.current.recap?.state).toBe('ready')
  })
  it('does not let an older response restore revoked data', async () => {
    const old = deferred<RecapDetail>()
    mock.get.mockReturnValueOnce(old.promise).mockRejectedValueOnce(new ApiError('Denied', 403, null))
    const { result } = renderHook(() => useRecap('recap', 0))
    act(() => { document.dispatchEvent(new Event('visibilitychange')) })
    await waitFor(() => expect(result.current.error).toContain('unavailable'))
    await act(async () => { old.resolve(detail('ready')) })
    expect(result.current.recap).toBeNull()
  })
  it('clears already loaded data after authoritative denial', async () => {
    mock.get.mockResolvedValueOnce(detail('ready')).mockRejectedValueOnce(new ApiError('Gone', 404, null))
    const { result } = renderHook(() => useRecap('recap', 0))
    await waitFor(() => expect(result.current.recap?.state).toBe('ready'))
    act(() => { document.dispatchEvent(new Event('visibilitychange')) })
    await waitFor(() => expect(result.current.recap).toBeNull())
  })
})
