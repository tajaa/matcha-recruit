import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
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
  it('bundles a deep-linked finding before either the list or task has resolved', async () => {
    const initial = deferred<AgentTaskDetail>()
    mock.get.mockReturnValue(initial.promise)
    const { result } = await opened('i1')
    expect(mock.get).toHaveBeenCalledWith('t1', 'i1')
    expect(mock.item).not.toHaveBeenCalled()
    await act(async () => { initial.resolve(task({ selected_item: finding('new') })) })
    expect(result.current.item?.title).toBe('The Avery')
    expect(mock.item).not.toHaveBeenCalled()
  })

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
    mock.get.mockResolvedValue(task({ selected_item: finding('new') }))
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
    mock.get.mockResolvedValue(task({ selected_item_error: 'Finding not found.' }))
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
    mock.get.mockResolvedValue(task({ selected_item: finding('new') }))
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

describe('useTasks polling', () => {
  afterEach(() => vi.useRealTimers())

  it('leaves a job-search detail and its leads to useJobSearch, while refreshing the Tasks list', async () => {
    vi.useFakeTimers()
    mock.get.mockResolvedValue(task({ engine: 'job_search', job_search_id: 's1', status: 'running' }))
    const { result } = await opened('l1')
    expect(result.current.detail?.job_search_id).toBe('s1')
    expect(mock.item).not.toHaveBeenCalled()
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000) })
    expect(mock.status).not.toHaveBeenCalled()
    expect(mock.get).toHaveBeenCalledTimes(1)
    expect(mock.list).toHaveBeenCalledTimes(2)
  })

  it('still polls ordinary running tasks at their usual pace', async () => {
    vi.useFakeTimers()
    mock.get.mockResolvedValue(task({ status: 'running' }))
    mock.status.mockResolvedValue({ id: 't1', status: 'running', fingerprint: 'f1' })
    await opened(null)
    await act(async () => { await vi.advanceTimersByTimeAsync(4_000) })
    expect(mock.status).toHaveBeenCalledWith('t1')
  })
})

describe('Tasks history', () => {
  it('keeps older pages across recent refreshes, including one overlapping a page load', async () => {
    const recent = { id: 'new', status: 'done', created_at: '2026-10-17T00:00:00+00:00' }
    const older = { id: 'old', status: 'done', created_at: '2026-10-16T00:00:00+00:00' }
    mock.list.mockResolvedValue({ tasks: [recent], next_cursor: 'next' })
    const { result } = renderHook(() => useTasks(undefined, null))
    await act(async () => {})
    const history = deferred<{ tasks: typeof older[]; next_cursor: null }>()
    mock.list.mockReturnValueOnce(history.promise)
    let loading = Promise.resolve()
    act(() => { loading = result.current.loadOlder() })
    await act(async () => { await result.current.loadList() })
    await act(async () => { history.resolve({ tasks: [older], next_cursor: null }); await loading })
    expect(result.current.list?.tasks.map((t) => t.id)).toEqual(['new', 'old'])
    await act(async () => { await result.current.loadList() })
    expect(result.current.list?.tasks.map((t) => t.id)).toEqual(['new', 'old'])
    expect(result.current.list?.next_cursor).toBeNull()
  })

  it('retries a failed history page and prevents duplicate page requests', async () => {
    mock.list.mockResolvedValueOnce({ tasks: [], next_cursor: 'next' })
    const { result } = renderHook(() => useTasks(undefined, null))
    await act(async () => {})
    mock.list.mockRejectedValueOnce(new Error('offline'))
    await act(async () => { await result.current.loadOlder() })
    expect(result.current.olderError).toBe("Couldn't load older tasks.")
    const page = deferred<{ tasks: []; next_cursor: null }>()
    mock.list.mockReturnValueOnce(page.promise)
    let loading = Promise.resolve()
    act(() => { loading = result.current.loadOlder(); void result.current.loadOlder() })
    expect(mock.list).toHaveBeenCalledTimes(3)
    await act(async () => { page.resolve({ tasks: [], next_cursor: null }); await loading })
    expect(result.current.olderError).toBeNull()
    expect(result.current.loadingOlder).toBe(false)
  })
})
