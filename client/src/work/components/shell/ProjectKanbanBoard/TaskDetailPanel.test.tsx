import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import type { MWProjectTask } from '../../../types'
import TaskDetailPanel from './TaskDetailPanel'

const { shot } = vi.hoisted(() => ({
  shot: { id: 'a1', filename: 'shot.png', content_type: 'image/png', storage_url: 'https://cdn.example.com/a1.png' },
}))

vi.mock('../../../api/matchaWork', () => ({
  listTaskFiles: () => Promise.resolve([shot]),
  uploadTaskFile: vi.fn(),
  deleteTaskFile: vi.fn(),
  TASK_FILE_MAX_BYTES: 10_000_000,
  TASK_FILE_ALLOWED_EXT: ['png'],
}))
vi.mock('./TaskViewerExtras', () => ({ default: () => null }))
vi.mock('./TaskCommitSuggestions', () => ({ default: () => null }))
vi.mock('./ResearchWithAssistant', () => ({ default: () => null }))
vi.mock('./useTaskDetailPanel', () => ({
  useTaskDetailPanel: () => ({
    setAttachments: vi.fn(),
    subtasks: [],
    subtasksLoading: false,
    newSubtask: '',
    setNewSubtask: vi.fn(),
    description: 'draft',
    setDescription: vi.fn(),
    handleCopyTicket: vi.fn(),
  }),
}))

const task = { id: 't1', title: 'Clear stale review state', board_column: 'todo', priority: 'medium', attachments: [shot] } as unknown as MWProjectTask
let onClose: () => void

beforeEach(() => {
  onClose = vi.fn()
  render(
    <TaskDetailPanel projectId="p1" task={task} onClose={onClose} onPatched={vi.fn()} onDelete={vi.fn()} onSubtaskCountChange={vi.fn()} />,
  )
})

describe('TaskDetailPanel pop-out', () => {
  it('is a modal dialog that closes on Escape', () => {
    expect(screen.getByRole('dialog', { name: 'Clear stale review state' })).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes from the backdrop but not from inside the dialog', () => {
    fireEvent.mouseDown(screen.getByRole('dialog'))
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.mouseDown(screen.getByRole('dialog').parentElement!)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('lets Escape close an open attachment preview before the ticket', () => {
    fireEvent.click(screen.getByTitle('shot.png'))
    expect(screen.getByLabelText('Close preview')).toBeTruthy()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByLabelText('Close preview')).toBeNull()
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
