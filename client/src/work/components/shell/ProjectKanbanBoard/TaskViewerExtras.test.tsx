import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import TaskViewerExtras from './TaskViewerExtras'
import type { MWProjectTask } from '../../../types'

const mock = vi.hoisted(() => ({
  capabilities: vi.fn(), history: vi.fn(), staged: vi.fn(), patch: vi.fn(),
  round: vi.fn(), summarize: vi.fn(),
}))
vi.mock('../../../api/matchaWork', () => ({
  getBoardCapabilities: mock.capabilities,
  getTaskHistory: mock.history,
  listStagedOutreach: mock.staged,
  updateProjectTask: mock.patch,
  startTaskRound: mock.round,
  summarizeTask: mock.summarize,
}))

const task = {
  id: 'task-1', project_id: 'project-1', title: 'Fix it', description: null,
  board_column: 'todo', priority: 'medium', status: 'pending', assigned_to: null,
  due_date: null, completed_at: null, created_at: '', updated_at: '',
  progress_note: null, category: null, element_id: null,
} as MWProjectTask

function mount() {
  const onPatched = vi.fn()
  render(<TaskViewerExtras projectId="project-1" task={task} canEdit historyVersion={0} onPatched={onPatched} onRoundCreated={vi.fn()} />)
  return onPatched
}

beforeEach(() => {
  vi.clearAllMocks()
  mock.capabilities.mockResolvedValue({ capabilities: { 'project-1': [] } })
  mock.history.mockResolvedValue([])
  mock.patch.mockResolvedValue(task)
})

describe('task viewer fields and outreach', () => {
  it('rejects a PR URL without a scheme before PATCH', async () => {
    mount()
    const input = screen.getByPlaceholderText('https://github.com/…/pull/123')
    fireEvent.change(input, { target: { value: 'github.com/org/repo/pull/1' } })
    fireEvent.blur(input)
    expect(await screen.findByText('PR URL must start with http:// or https://.')).toBeInTheDocument()
    expect(mock.patch).not.toHaveBeenCalled()
  })

  it('clears the AutoPR model with null', async () => {
    mount()
    fireEvent.change(screen.getByLabelText('AutoPR model'), { target: { value: 'gpt-6-astra' } })
    await waitFor(() => expect(mock.patch).toHaveBeenCalledWith('project-1', 'task-1', { autopr_model: 'gpt-6-astra' }))
    fireEvent.change(screen.getByLabelText('AutoPR model'), { target: { value: '' } })
    await waitFor(() => expect(mock.patch).toHaveBeenCalledWith('project-1', 'task-1', { autopr_model: null }))
  })

  it('renders a missing outreach grant as not enabled', async () => {
    mount()
    expect(await screen.findByText('Outreach is not enabled for this board.')).toBeInTheDocument()
    expect(mock.staged).not.toHaveBeenCalled()
  })
})
