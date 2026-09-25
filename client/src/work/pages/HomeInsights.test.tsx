import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ActivityList, AssignedTaskList } from './HomeInsights'
import type { MWOpenTask } from '../api/matchaWork/dashboard'

const task = (id: string, title: string, isSubtask = false): MWOpenTask => ({
  id, project_id: 'project-one', title, priority: isSubtask ? '' : 'high',
  status: isSubtask ? 'pending' : 'open', due_date: null, progress_note: null,
  assigned_to: 'me', created_by: 'other', updated_at: '', project_title: 'Project',
  project_type: 'general', is_subtask: isSubtask,
  ...(isSubtask ? { parent_task_id: 'parent', parent_title: 'Parent task' } : {}),
})

describe('Home dashboard', () => {
  it('preserves server task order and identifies subtasks by their parent', () => {
    render(<MemoryRouter><AssignedTaskList tasks={[task('first', 'First task'), task('second', 'Checklist item', true)]} base="/espresso" /></MemoryRouter>)
    const links = screen.getAllByRole('link')
    expect(links[0]).toHaveTextContent('First task')
    expect(links[1]).toHaveTextContent('Checklist item')
    expect(links[1]).toHaveTextContent('Parent task')
    expect(links[1]).toHaveTextContent('Subtask')
  })

  it('renders an empty activity response without error', () => {
    render(<MemoryRouter><ActivityList items={[]} base="/espresso" /></MemoryRouter>)
    expect(screen.getByText('No recent activity yet.')).toBeInTheDocument()
  })
})
