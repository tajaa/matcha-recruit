import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import EmailSnapshotWizard from './EmailSnapshotWizard'
import type { AgentEmail } from '../../types'

const mock = vi.hoisted(() => ({ projects: vi.fn(), tasks: vi.fn(), snapshot: vi.fn() }))
vi.mock('../../api/matchaWork', () => ({ listProjects: mock.projects, listProjectTasks: mock.tasks, agentSnapshotEmails: mock.snapshot }))

const emails: AgentEmail[] = Array.from({ length: 11 }, (_, index) => ({ id: `mail-${index}`, subject: `Subject ${index}`, from: 'sender@test.com', body: 'Body', date: 'Today' }))

beforeEach(() => {
  vi.clearAllMocks()
  mock.projects.mockResolvedValue([{ id: 'project-1', title: 'Project' }])
  mock.tasks.mockResolvedValue([{ id: 'task-1', title: 'Task', status: 'pending' }])
})

describe('email task snapshots', () => {
  it('blocks an eleventh email before the request', () => {
    render(<EmailSnapshotWizard emails={emails} maxEmails={10} initialIds={[]} onClose={() => {}} />)
    const checkboxes = screen.getAllByRole('checkbox')
    checkboxes.forEach((checkbox) => fireEvent.click(checkbox))
    expect(screen.getByText('Emails (10/10)')).toBeTruthy()
    expect(screen.getByText('Select at most 10 emails.')).toBeTruthy()
    expect(mock.snapshot).not.toHaveBeenCalled()
  })

  it('shows skipped reasons next to attached files', async () => {
    mock.snapshot.mockResolvedValue({ files: [{ id: 'file-1', filename: 'email-mail-0.md' }], skipped: [{ email_id: 'mail-1', reason: 'fetch_failed' }] })
    render(<EmailSnapshotWizard emails={emails.slice(0, 2)} maxEmails={10} initialIds={[]} onClose={() => {}} />)
    fireEvent.click(screen.getByLabelText('Subject 0'))
    fireEvent.click(screen.getByLabelText('Subject 1'))
    fireEvent.change(await screen.findByLabelText('Project'), { target: { value: 'project-1' } })
    fireEvent.change(await screen.findByLabelText('Task'), { target: { value: 'task-1' } })
    fireEvent.click(screen.getByText('Attach snapshots'))
    await waitFor(() => expect(mock.snapshot).toHaveBeenCalledWith(['mail-0', 'mail-1'], 'project-1', 'task-1'))
    expect(await screen.findByText('Attached: email-mail-0.md')).toBeTruthy()
    expect(screen.getByText('Skipped mail-1: fetch failed')).toBeTruthy()
  })
})
