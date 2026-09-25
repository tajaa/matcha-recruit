import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../../../api/client'
import { useAgentTaskDraft } from './useAgentTaskDraft'

const mock = vi.hoisted(() => ({ start: vi.fn(), get: vi.fn() }))
vi.mock('../../../api/matchaWork', () => ({ startAgentTaskDraft: mock.start, getAgentTaskDraft: mock.get }))

beforeEach(() => { vi.clearAllMocks(); vi.useFakeTimers(); mock.start.mockResolvedValue({ run_id: 'run-1', status: 'queued' }) })
afterEach(() => vi.useRealTimers())

describe('repository task drafting', () => {
  it('shows connect-a-repo guidance for 412', async () => {
    mock.start.mockRejectedValue(new ApiError('repository required', 412, { detail: { code: 'repository_required' } }))
    const { result } = renderHook(() => useAgentTaskDraft('project-1', vi.fn()))
    await act(async () => { await result.current.start('fix the task') })
    expect(result.current.error).toContain('Connect a GitHub repository')
  })

  it('stops polling after a terminal result', async () => {
    mock.get.mockResolvedValueOnce({ run_id: 'run-1', status: 'running' })
      .mockResolvedValueOnce({ run_id: 'run-1', status: 'completed', draft: { title: 'Fix' } })
    const onDraft = vi.fn()
    const { result } = renderHook(() => useAgentTaskDraft('project-1', onDraft))
    await act(async () => { await result.current.start('fix the task') })
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(onDraft).toHaveBeenCalledOnce()
    await act(async () => { await vi.advanceTimersByTimeAsync(4000) })
    expect(mock.get).toHaveBeenCalledTimes(2)
  })

  it('stops polling when the board unmounts', async () => {
    mock.get.mockResolvedValue({ run_id: 'run-1', status: 'running' })
    const { result, unmount } = renderHook(() => useAgentTaskDraft('project-1', vi.fn()))
    await act(async () => { await result.current.start('fix the task') })
    unmount()
    await act(async () => { await vi.advanceTimersByTimeAsync(4000) })
    expect(mock.get).toHaveBeenCalledOnce()
  })
})
