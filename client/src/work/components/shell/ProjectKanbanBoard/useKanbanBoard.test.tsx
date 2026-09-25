import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useKanbanBoard } from './useKanbanBoard'

const mock = vi.hoisted(() => ({ bundle: vi.fn(), tasks: vi.fn(), connection: vi.fn(), suggestions: vi.fn() }))
vi.mock('../../../api/matchaWork', () => ({ getProjectBundle: mock.bundle, listProjectTasks: mock.tasks, getGithubConnection: mock.connection, listCommitSuggestions: mock.suggestions }))
vi.mock('../../../../hooks/useMe', () => ({ useMe: () => ({ me: null }) }))
vi.mock('../../../api/projectSocket', () => ({
  ProjectSocket: class {
    connect() {}
    joinProject() {}
    disconnect() {}
  },
}))

beforeEach(() => {
  vi.clearAllMocks()
  mock.bundle.mockResolvedValue({ tasks: [], collaborators: [], done_total: 0 })
  mock.connection.mockResolvedValue({ connected: false })
  mock.suggestions.mockResolvedValue([])
})

describe('board project open', () => {
  it('loads the bundle once instead of separate task and collaborator requests', async () => {
    const { result } = renderHook(() => useKanbanBoard('project-1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(mock.bundle).toHaveBeenCalledOnce()
    expect(mock.bundle).toHaveBeenCalledWith('project-1')
    expect(mock.tasks).not.toHaveBeenCalled()
  })

  it('loads earlier Done cards only when expanded', async () => {
    const done = { id: 'old', board_column: 'done', title: 'Earlier', completed_at: '2026-01-01' }
    mock.bundle.mockResolvedValue({ tasks: [], collaborators: [], done_total: 1 })
    mock.tasks.mockResolvedValue([done])
    const { result } = renderHook(() => useKanbanBoard('project-1'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.visible).toHaveLength(0)
    await act(async () => { await result.current.expandDone() })
    expect(mock.tasks).toHaveBeenCalledWith('project-1', 'all')
    expect(result.current.visible).toHaveLength(1)
    await act(async () => { await result.current.expandDone() })
    expect(result.current.visible).toHaveLength(0)
  })
})
