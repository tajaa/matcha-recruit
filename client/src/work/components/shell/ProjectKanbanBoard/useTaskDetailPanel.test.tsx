import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../../../api/client'
import type { MWProjectTask, MWSubtask } from '../../../types'
import { useTaskDetailPanel } from './useTaskDetailPanel'

const mock = vi.hoisted(() => ({
  approve: vi.fn(), reject: vi.fn(), subtasks: vi.fn(), update: vi.fn(),
}))
vi.mock('../../../api/matchaWork', () => ({
  approveProjectTask: mock.approve,
  rejectProjectTask: mock.reject,
  listSubtasks: mock.subtasks,
  updateSubtask: mock.update,
}))

const task = { id: 'task-1', description: null, attachments: [] } as unknown as MWProjectTask
const sub = { id: 'sub-1', title: 'Done item', is_done: true } as MWSubtask

beforeEach(() => {
  vi.clearAllMocks()
  mock.subtasks.mockResolvedValue([sub])
  mock.update.mockImplementation(async (_project: string, _task: string, _sub: string, patch: object) => ({ ...sub, ...patch }))
})

function mount() {
  return renderHook(() => useTaskDetailPanel({ projectId: 'project-1', task, onPatched: vi.fn(), onSubtaskCountChange: vi.fn() }))
}

describe('task review and checklist', () => {
  it('blocks an empty rejection note before the request', async () => {
    const { result } = mount()
    await act(async () => { await result.current.handleReject() })
    expect(mock.reject).not.toHaveBeenCalled()
  })

  it('explains an approve 400 when the task moved out of Review', async () => {
    mock.approve.mockRejectedValue(new ApiError('bad state', 400, {}))
    const { result } = mount()
    await act(async () => { await result.current.handleApprove() })
    expect(result.current.reviewError).toContain('Move this task to Review first')
  })

  it('uses distinct bodies for plain uncheck and rejection with reason', async () => {
    const { result } = mount()
    await waitFor(() => expect(result.current.subtasks).toHaveLength(1))
    await act(async () => { await result.current.toggleSubtask(sub) })
    expect(mock.update).toHaveBeenCalledWith('project-1', 'task-1', 'sub-1', { is_done: false })
    await act(async () => { await result.current.rejectSubtask(sub, 'wrong commit') })
    expect(mock.update).toHaveBeenCalledWith('project-1', 'task-1', 'sub-1', { is_done: false, reason: 'wrong commit' })
  })
})
