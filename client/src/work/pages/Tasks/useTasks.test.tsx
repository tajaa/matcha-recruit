import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../../api/client'
import { useTasks } from './useTasks'
import type { AgentTaskDetail, AgentTaskItemDetail } from '../../types'

const mock = vi.hoisted(() => ({
  list: vi.fn(), get: vi.fn(), status: vi.fn(), item: vi.fn(), update: vi.fn(), round: vi.fn(),
}))
vi.mock('../../api/matchaWork/agentTasks', () => ({
  listAgentTasks: mock.list,
  getAgentTask: mock.get,
  getAgentTaskStatus: mock.status,
  getAgentTaskItem: mock.item,
  updateAgentTaskItem: mock.update,
  startAgentTaskRound: mock.round,
  cancelAgentTask: vi.fn(),
  deleteAgentTask: vi.fn(),
}))

const task = (over: Partial<AgentTaskDetail> = {}): AgentTaskDetail => ({
  id: 't1', status: 'done', fingerprint: 'f1', rounds: [], items: [], ...over,
})
const finding = (user_state: string): AgentTaskItemDetail => ({ id: 'i1', title: 'The Avery', user_state })

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

async function opened(itemId: string | null) {
  mock.list.mockResolvedValue({ tasks: [], usage: null })
  const hook = renderHook(() => useTasks('t1', itemId))
  await act(async () => {})
  return hook
}

describe('useTasks reads and changes', () => {
  it("doesn't let a read that left before \"Search more\" put the finished task back", async () => {
    mock.get.mockResolvedValueOnce(task())
    const { result } = await opened(null)
    expect(result.current.detail?.status).toBe('done')

    const old = deferred<AgentTaskDetail>()
    mock.get.mockReturnValueOnce(old.promise)
    let reading = Promise.resolve()
    act(() => { reading = result.current.loadDetail('t1') })
    mock.round.mockResolvedValue(task({ status: 'queued', fingerprint: 'f2' }))
    await act(async () => { await result.current.startRound('more') })
    expect(result.current.detail?.status).toBe('queued')

    await act(async () => { old.resolve(task()); await reading })
    expect(result.current.detail?.status).toBe('queued') // still live, so it keeps polling
  })

  it("doesn't let a finding read that left before a Save undo it", async () => {
    mock.get.mockResolvedValue(task())
    mock.item.mockResolvedValueOnce(finding('new'))
    const { result } = await opened('i1')
    expect(result.current.item?.user_state).toBe('new')

    const old = deferred<AgentTaskItemDetail>()
    mock.item.mockReturnValueOnce(old.promise)
    let reading = Promise.resolve()
    act(() => { reading = result.current.reloadItem() })
    mock.update.mockResolvedValue(finding('saved'))
    await act(async () => { await result.current.setItemState('saved', 'i1') })
    expect(result.current.item?.user_state).toBe('saved')

    await act(async () => { old.resolve(finding('new')); await reading })
    expect(result.current.item?.user_state).toBe('saved')
  })

  it('keeps only the newest of two reads of the same task', async () => {
    mock.get.mockResolvedValueOnce(task())
    const { result } = await opened(null)
    const first = deferred<AgentTaskDetail>()
    const second = deferred<AgentTaskDetail>()
    mock.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    let a = Promise.resolve()
    let b = Promise.resolve()
    act(() => { a = result.current.loadDetail('t1'); b = result.current.loadDetail('t1') })
    await act(async () => { second.resolve(task({ fingerprint: 'new' })); await b })
    await act(async () => { first.resolve(task({ fingerprint: 'old' })); await a })
    expect(result.current.detail?.fingerprint).toBe('new')
  })
})

describe('useTasks finding errors', () => {
  it("says a finding couldn't load, with no task-wide error, and clears it on a retry", async () => {
    mock.get.mockResolvedValue(task())
    mock.item.mockRejectedValueOnce(new ApiError('Finding not found.', 404, {}))
    const { result } = await opened('i1')
    expect(result.current.item).toBeNull()
    expect(result.current.itemLoadError).toBe('Finding not found.')
    expect(result.current.error).toBeNull()

    mock.item.mockResolvedValueOnce(finding('new'))
    await act(async () => { await result.current.reloadItem() })
    expect(result.current.itemLoadError).toBeNull()
    expect(result.current.item?.title).toBe('The Avery')

    // A refresh that misses while it's on screen keeps what's there.
    mock.item.mockRejectedValueOnce(new Error('offline'))
    await act(async () => { await result.current.reloadItem() })
    expect(result.current.item?.title).toBe('The Avery')
    expect(result.current.itemLoadError).toBeNull()
  })

  it('reports a change made from the pane in the pane', async () => {
    mock.get.mockResolvedValue(task())
    mock.item.mockResolvedValue(finding('new'))
    const { result } = await opened('i1')

    mock.update.mockRejectedValueOnce(new ApiError('Too many changes.', 429, {}))
    await act(async () => { await result.current.setItemState('saved', 'i1') })
    expect(result.current.itemError).toBe('Too many changes.')
    expect(result.current.error).toBeNull()

    mock.round.mockRejectedValueOnce(new ApiError('No units left this month.', 402, {}))
    await act(async () => { await result.current.startRound('more', '', ['i1'], 'i1') })
    expect(result.current.itemError).toBe('No units left this month.')
    expect(result.current.error).toBeNull()

    // From the task itself, it's the task's error.
    mock.round.mockRejectedValueOnce(new ApiError('No units left this month.', 402, {}))
    await act(async () => { await result.current.startRound('more') })
    expect(result.current.error).toBe('No units left this month.')
    expect(result.current.itemError).toBeNull()
  })
})
