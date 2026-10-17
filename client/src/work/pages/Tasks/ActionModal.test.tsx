import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../../api/client'
import ActionModal from './ActionModal'
import { RUNNING_READS, RUNNING_READ_MS } from '../../components/tasks/tasksLogic'
import type { AgentTaskAction, AgentTaskActionRun } from '../../types'

const mock = vi.hoisted(() => ({ propose: vi.fn(), confirm: vi.fn(), cancel: vi.fn() }))
vi.mock('../../api/matchaWork/agentTasks', () => ({
  proposeAgentTaskAction: mock.propose,
  confirmAgentTaskAction: mock.confirm,
  cancelAgentTaskAction: mock.cancel,
}))

afterEach(() => { vi.useRealTimers() })

const apply: AgentTaskAction = { key: 'apply', label: 'Apply', icon: 'link', params: [] }
const proposed: AgentTaskActionRun = {
  id: 'run-1', status: 'proposed', confirm_label: 'Open the application',
  preview: { title: 'Apply to The Avery', lines: [{ label: 'Opens', value: 'averysf.com' }] },
}
const running: AgentTaskActionRun = { ...proposed, status: 'running' }
const done: AgentTaskActionRun = {
  ...proposed, status: 'done', result: { headline: 'Ready to finish', url: 'https://averysf.com/apply' },
}

function openSheet(onClose = vi.fn()) {
  const view = render(<ActionModal taskId="t1" itemId="i1" itemTitle="The Avery" action={apply} onClose={onClose} />)
  return { ...view, onClose }
}

describe('ActionModal', () => {
  it('reads a running yes again until it is done, and never says nothing was done', async () => {
    vi.useFakeTimers()
    mock.propose.mockResolvedValue(proposed)
    mock.confirm.mockResolvedValueOnce(running).mockResolvedValueOnce(running).mockResolvedValueOnce(done)
    const { onClose } = openSheet()
    await act(async () => {})
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open the application' })) })
    expect(screen.getByText('Working on it…')).toBeTruthy()
    expect(screen.queryByText(/Nothing was done/)).toBeNull()

    await act(async () => { await vi.advanceTimersByTimeAsync(RUNNING_READ_MS * 2) })
    expect(mock.confirm).toHaveBeenCalledTimes(3)
    expect(mock.confirm).toHaveBeenLastCalledWith('run-1')
    expect(screen.getByText('Ready to finish')).toBeTruthy()
    expect(screen.getByRole('link', { name: /Open/ }).getAttribute('href')).toBe('https://averysf.com/apply')

    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(onClose).toHaveBeenCalledWith(true)
  })

  it("says it's still going when it hasn't finished after a minute, and can check again", async () => {
    vi.useFakeTimers()
    mock.propose.mockResolvedValue(proposed)
    mock.confirm.mockResolvedValue(running)
    const { onClose } = openSheet()
    await act(async () => {})
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open the application' })) })
    await act(async () => { await vi.advanceTimersByTimeAsync(RUNNING_READ_MS * (RUNNING_READS + 1)) })

    expect(mock.confirm).toHaveBeenCalledTimes(RUNNING_READS + 1)
    expect(screen.getByText(/It's still going/)).toBeTruthy()
    expect(screen.queryByText(/Nothing was done/)).toBeNull()

    mock.confirm.mockResolvedValue(done)
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Check again' })) })
    expect(screen.getByText('Ready to finish')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(onClose).toHaveBeenCalledWith(true)
  })

  it("says it's still going when checking on a running yes fails", async () => {
    vi.useFakeTimers()
    mock.propose.mockResolvedValue(proposed)
    mock.confirm.mockResolvedValueOnce(running).mockRejectedValueOnce(new Error('offline'))
    openSheet()
    await act(async () => {})
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open the application' })) })
    await act(async () => { await vi.advanceTimersByTimeAsync(RUNNING_READ_MS) })
    expect(screen.getByText(/It's still going/)).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toBe("Couldn't check on it just now.")
    expect(screen.getByRole('button', { name: 'Check again' })).toBeTruthy()
  })

  it('withdraws a proposal that arrives after the sheet was closed', async () => {
    let resolve!: (run: AgentTaskActionRun) => void
    mock.propose.mockReturnValue(new Promise<AgentTaskActionRun>((r) => { resolve = r }))
    mock.cancel.mockResolvedValue({ ...proposed, status: 'cancelled' })
    const { unmount } = openSheet()
    await act(async () => {})
    expect(mock.propose).toHaveBeenCalledOnce()
    unmount()
    expect(mock.cancel).not.toHaveBeenCalled()

    await act(async () => { resolve(proposed) })
    expect(mock.cancel).toHaveBeenCalledWith('run-1')
  })

  it('withdraws a proposal left in review when it closes', async () => {
    mock.propose.mockResolvedValue(proposed)
    mock.cancel.mockResolvedValue({ ...proposed, status: 'cancelled' })
    const { unmount, onClose } = openSheet()
    await act(async () => {})
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalledWith(false)
    unmount()
    expect(mock.cancel).toHaveBeenCalledWith('run-1')
  })

  it('offers to try again when it could not say what it would do', async () => {
    mock.propose.mockRejectedValueOnce(new ApiError('Too many at once. Wait a minute.', 429, {})).mockResolvedValueOnce(proposed)
    mock.cancel.mockResolvedValue({ ...proposed, status: 'cancelled' })
    openSheet()
    await act(async () => {})
    expect(screen.getByRole('alert').textContent).toBe('Too many at once. Wait a minute.')

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Try again' })) })
    expect(mock.propose).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('button', { name: 'Open the application' })).toBeTruthy()
  })
})
