import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import TaskCommitSuggestions from './TaskCommitSuggestions'

const mock = vi.hoisted(() => ({ pending: vi.fn(), accepted: vi.fn(), accept: vi.fn(), dismiss: vi.fn() }))
vi.mock('../../../api/matchaWork', () => ({
  listCommitSuggestions: mock.pending, listCommitCompletions: mock.accepted,
  acceptCommitSuggestion: mock.accept, dismissCommitSuggestion: mock.dismiss,
}))

const row = (id: string, subtaskId: string) => ({
  id, task_id: 'task-1', subtask_id: subtaskId, commit_short_sha: id, commit_message: `commit ${id}`,
})

beforeEach(() => {
  vi.clearAllMocks()
  mock.accepted.mockResolvedValue([])
  mock.dismiss.mockResolvedValue({})
})

describe('TaskCommitSuggestions', () => {
  it('reports remaining pending work as distinct subtasks, not suggestions', async () => {
    mock.pending
      .mockResolvedValueOnce([row('a', 'sub-1'), row('b', 'sub-1'), row('c', 'sub-2')])
      .mockResolvedValueOnce([row('b', 'sub-1'), row('c', 'sub-2')])
    const onResolved = vi.fn()
    render(<TaskCommitSuggestions projectId="project-1" taskId="task-1" canEdit onAccepted={vi.fn()} onResolved={onResolved} />)
    await screen.findByText('a · commit a')
    fireEvent.click(screen.getAllByText('Dismiss')[0])
    await waitFor(() => expect(onResolved).toHaveBeenCalledWith(2))
  })
})
