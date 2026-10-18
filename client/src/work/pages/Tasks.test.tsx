import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { WorkSurfaceProvider } from '../routes/WorkSurfaceContext'
import type { AgentTaskDetail } from '../types'
import type { JobLeadDetail, JobSearchDetail } from '../api/matchaWork/jobSearch'
import Tasks from './Tasks'
import JobSearchRedirect from './JobSearch'

const mock = vi.hoisted(() => ({
  list: vi.fn(), task: vi.fn(), item: vi.fn(), remove: vi.fn(), search: vi.fn(), lead: vi.fn(),
  searches: vi.fn(), create: vi.fn(), update: vi.fn(), email: vi.fn(), status: vi.fn(), taskStatus: vi.fn(),
  lookup: vi.fn(), setup: vi.fn(), tasksEnabled: true, jobSearchEnabled: true, wide: false,
}))
vi.mock('../../hooks/useMe', () => ({ useMe: () => ({ isPersonal: true }) }))
vi.mock('../hooks/useEntitlements', () => ({ useEntitlements: () => mock }))
vi.mock('../hooks/useTasksSummary', () => ({ notifyTasksChanged: vi.fn() }))
vi.mock('../../api/profileResume', () => ({ getMyResume: () => Promise.resolve(null), uploadMyResume: vi.fn() }))
vi.mock('../api/matchaWork/agentTasks', () => ({
  getAgentTaskForSearch: mock.lookup, listAgentTasks: mock.list, getAgentTask: mock.task, getAgentTaskItem: mock.item, deleteAgentTask: mock.remove,
  getAgentTaskStatus: mock.taskStatus, updateAgentTaskItem: vi.fn(), startAgentTaskRound: vi.fn(), cancelAgentTask: vi.fn(),
}))
vi.mock('../api/matchaWork/jobSearch', () => ({
  getJobSearchSetup: mock.setup, listJobSearches: mock.searches, getJobSearch: mock.search, getJobLead: mock.lead,
  createJobSearch: mock.create, updateJobLead: mock.update, draftJobEmail: mock.email,
  getJobSearchStatus: mock.status, redraftJobApproach: vi.fn(), rerankJobSearch: vi.fn(), widenJobSearch: vi.fn(),
  cancelJobSearch: vi.fn(), deleteJobSearch: vi.fn(),
}))

const pointer: AgentTaskDetail = {
  id: 't1', title: 'My job search', status: 'done', engine: 'job_search', job_search_id: 's1',
  fingerprint: 't-f1', items: [],
}
const lead: JobLeadDetail = {
  id: 'l1', title: 'COO', company: 'Example Co', location: 'Austin, TX', remote: false,
  source_url: 'https://example.com/jobs/coo', apply_url: null, posted_text: null,
  comp_line: '$250K', comp_status: 'posted', fit_score: 4, screen_status: 'relevant', rank: 1, rank_band: 0,
  flags: [], user_state: 'new', approach_status: 'done', email_draft_id: null, email_drafted_at: null,
  email_sent_at: null, description: 'Run operations', comp: null, pay_law_hint: null, screen_reason: null,
  fit_reasons: [], approach: { outreach: { subject: 'Hello', body: 'I would like to learn more.' } }, notes: '',
}
const search: JobSearchDetail = {
  id: 's1', title: 'COO roles', ask: 'COO roles in Austin', status: 'done', progress: null, error: null,
  lead_count: 1, posted_pay_count: 1, weights: null, use_resume: false, created_at: null, fit_floor: 4,
  fingerprint: 's-f1', leads: [lead],
}

function Location() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}{JSON.stringify(location.state)}</output>
}

function renderAt(path = '/espresso/tasks/t1') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <WorkSurfaceProvider value="espresso">
        <Routes>
          <Route path="/espresso/jobs/:searchId" element={<JobSearchRedirect />} />
          <Route path="/espresso/tasks" element={<Tasks />} />
          <Route path="/espresso/tasks/:taskId" element={<Tasks />} />
          <Route path="/espresso/assistant" element={<p>Assistant</p>} />
        </Routes>
        <Location />
      </WorkSurfaceProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mock.tasksEnabled = true
  mock.jobSearchEnabled = true
  mock.wide = false
  vi.stubGlobal('matchMedia', () => ({ matches: mock.wide }))
  localStorage.setItem('espresso-tasks-guide-seen', '1')
  localStorage.setItem('espresso-job-search-guide-seen', '1')
  mock.list.mockResolvedValue({ tasks: [pointer], usage: null })
  mock.task.mockResolvedValue(pointer)
  mock.search.mockResolvedValue(search)
  mock.lead.mockResolvedValue(lead)
  mock.lookup.mockResolvedValue({ ...pointer, id: 't2', job_search_id: 's2' })
  mock.setup.mockResolvedValue({ searches: [search], consent: { granted: true }, usage: null, available: true })
})

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('job searches in Tasks', () => {
  it('renders the search and its deep-linked job in Tasks, without generic item reads or a searches-list load', async () => {
    renderAt('/espresso/tasks/t1?item=l1')
    expect(await screen.findByRole('heading', { name: 'COO roles' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'COO' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/tasks/t1?item=l1')
    expect(screen.getByLabelText('Job search')).toBeInTheDocument()
    expect(mock.item).not.toHaveBeenCalled()
    expect(mock.searches).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Make document' })).not.toBeInTheDocument()
  })

  it('keeps a job search usable from its list row while task detail is still loading', async () => {
    mock.task.mockReturnValue(new Promise(() => {}))
    renderAt()
    expect(await screen.findByRole('heading', { name: 'COO roles' })).toBeInTheDocument()
  })

  it('refreshes the Tasks row when the search status changes, with only the search polling', async () => {
    vi.useFakeTimers()
    mock.task.mockResolvedValue({ ...pointer, status: 'running' })
    mock.search.mockResolvedValueOnce({ ...search, status: 'discovering' }).mockResolvedValue(search)
    mock.status.mockResolvedValue({ id: 's1', status: 'done', fingerprint: 's-f2', lead_count: 1 })
    renderAt()
    await act(async () => {})
    const reads = mock.list.mock.calls.length
    mock.task.mockResolvedValue(pointer)
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000) })
    expect(mock.status).toHaveBeenCalledTimes(1)
    expect(mock.taskStatus).not.toHaveBeenCalled()
    expect(mock.list).toHaveBeenCalledTimes(reads)
    expect(mock.task).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('button', { name: /My job search/ })).toHaveTextContent('Done')
  })

  it('keeps field focus when Tasks polls while the new-search form is open', async () => {
    vi.useFakeTimers()
    renderAt()
    await act(async () => {})
    fireEvent.click(screen.getByRole('button', { name: 'New job search…' }))
    await act(async () => {})
    const field = screen.getByLabelText('What are you looking for?')
    field.focus()
    fireEvent.change(field, { target: { value: 'Keep typing' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000) })
    expect(field).toHaveFocus()
    expect(field).toHaveValue('Keep typing')
    expect(mock.setup).toHaveBeenCalledTimes(1)
    expect(mock.searches).not.toHaveBeenCalled()
  })

  it('opens older job searches through task history and retains them across refreshes', async () => {
    mock.list.mockResolvedValueOnce({ tasks: [pointer], next_cursor: 'older' })
      .mockResolvedValueOnce({ tasks: [{ ...pointer, id: 'old-task', job_search_id: 'old-search', title: 'Older search' }], next_cursor: null })
      .mockResolvedValue({ tasks: [pointer], next_cursor: 'older' })
    renderAt('/espresso/tasks')
    fireEvent.click(await screen.findByRole('button', { name: 'Load older tasks' }))
    const older = await screen.findByRole('button', { name: /Older search/ })
    expect(mock.list).toHaveBeenCalledWith('older')
    fireEvent.click(older)
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/tasks/old-task')
  })

  it('does not duplicate a slow metadata read while marking an opened search seen', async () => {
    vi.useFakeTimers()
    const loading = new Promise<AgentTaskDetail>(() => {})
    mock.task.mockReturnValue(loading)
    mock.list.mockResolvedValue({ tasks: [{ ...pointer, unseen: true }] })
    renderAt()
    await act(async () => {})
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })
    expect(mock.task).toHaveBeenCalledTimes(1)
    expect(mock.search).toHaveBeenCalledTimes(1)
  })

  it('loads a search only once and does not immediately reload the task list', async () => {
    renderAt()
    await screen.findByRole('heading', { name: 'COO roles' })
    expect(mock.search).toHaveBeenCalledTimes(1)
    expect(mock.task).toHaveBeenCalledTimes(1)
    expect(mock.list).toHaveBeenCalledTimes(1)
  })

  it('retries persisting a finished search as seen while it remains open', async () => {
    vi.useFakeTimers()
    const running = { ...pointer, status: 'running', unseen: false }
    mock.list.mockResolvedValue({ tasks: [running] })
    mock.task.mockResolvedValueOnce(running).mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ ...pointer, unseen: false })
    mock.search.mockResolvedValueOnce({ ...search, status: 'discovering' }).mockResolvedValue(search)
    mock.status.mockResolvedValue({ id: 's1', status: 'done', fingerprint: 'finished', lead_count: 1 })
    renderAt()
    await act(async () => {})
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000) })
    expect(mock.task).toHaveBeenCalledTimes(2)
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000) })
    expect(mock.task).toHaveBeenCalledTimes(3)
    expect(screen.getByRole('button', { name: /My job search/ })).toHaveTextContent('Done')
    expect(screen.queryByLabelText('New')).not.toBeInTheDocument()
  })

  it('keeps a newly created search recoverable when list and lookup reads fail', async () => {
    mock.create.mockResolvedValue({ ...search, id: 's2' })
    // Tasks' own lookup misses, then the search's link tries again and offers a retry.
    mock.lookup.mockRejectedValueOnce(new Error('offline')).mockRejectedValueOnce(new Error('offline'))
    renderAt()
    fireEvent.click(await screen.findByRole('button', { name: 'New job search…' }))
    const form = await screen.findByRole('dialog', { name: 'New job search' })
    await act(async () => {})
    mock.list.mockRejectedValue(new Error('offline'))
    fireEvent.change(within(form).getByLabelText('What are you looking for?'), { target: { value: 'COO jobs' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Start search' }))
    await screen.findByRole('alert')
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/jobs/s2')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/espresso/tasks/t2'))
    expect(mock.lookup).toHaveBeenCalledWith('s2')
    expect(mock.create).toHaveBeenCalledTimes(1)
    expect(mock.setup).toHaveBeenCalledTimes(1)
    expect(mock.searches).not.toHaveBeenCalled()
  })

  it('opens a job-search row at /tasks and uses item for its selected job', async () => {
    renderAt('/espresso/tasks')
    fireEvent.click(await screen.findByRole('button', { name: /My job search/ }))
    expect(await screen.findByRole('heading', { name: 'COO roles' })).toBeInTheDocument()
    fireEvent.click(screen.getByText('COO'))
    expect(await screen.findByRole('heading', { name: 'COO' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/tasks/t1?item=l1')
    fireEvent.click(screen.getByRole('button', { name: 'Close the job' }))
    expect(screen.getByTestId('location')).not.toHaveTextContent('?item=')
  })

  it('auto-opens a job search on wide screens', async () => {
    mock.wide = true
    renderAt('/espresso/tasks')
    expect(await screen.findByRole('heading', { name: 'COO roles' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/tasks/t1')
  })

  it('closes a stale lead and returns to Tasks from the phone back arrow', async () => {
    renderAt('/espresso/tasks/t1?item=gone')
    expect(await screen.findByRole('heading', { name: 'COO roles' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('location')).not.toHaveTextContent('?item='))
    fireEvent.click(screen.getByRole('button', { name: 'All tasks' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/tasksnull')
  })

  it('shows the Tasks guide before the job guide, and lets the job guide reopen', async () => {
    localStorage.removeItem('espresso-tasks-guide-seen')
    localStorage.removeItem('espresso-job-search-guide-seen')
    renderAt()
    const tasksGuide = await screen.findByRole('dialog', { name: 'How Tasks works' })
    expect(screen.queryByRole('dialog', { name: 'How Job search works' })).not.toBeInTheDocument()
    fireEvent.click(within(tasksGuide).getByRole('button', { name: 'Skip' }))
    const jobGuide = await screen.findByRole('dialog', { name: 'How Job search works' })
    fireEvent.click(within(jobGuide).getByRole('button', { name: 'Skip' }))
    expect(localStorage.getItem('espresso-job-search-guide-seen')).toBe('1')
    fireEvent.click(screen.getByRole('button', { name: 'How Job search works' }))
    expect(screen.getByRole('dialog', { name: 'How Job search works' })).toBeInTheDocument()
  })

  it('deletes through Tasks after confirming the job-search-specific text', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mock.remove.mockImplementation(async () => { mock.list.mockResolvedValue({ tasks: [] }) })
    renderAt()
    fireEvent.click(await screen.findByRole('button', { name: 'Delete this search' }))
    await waitFor(() => expect(mock.remove).toHaveBeenCalledWith('t1'))
    expect(window.confirm).toHaveBeenCalledWith("Delete this task? Its jobs and drafts are removed. It still counts toward this month's units.")
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/espresso/tasksnull'))
  })

  it('keeps the search open and shows a failed task deletion', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mock.remove.mockRejectedValue(new Error('offline'))
    renderAt()
    fireEvent.click(await screen.findByRole('button', { name: 'Delete this search' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't delete this task.")
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/tasks/t1')
  })

  it('disables lead mutations during task deletion and restores them when deletion fails', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mock.lead.mockResolvedValue({ ...lead, approach: { ...lead.approach, summary: 'Approach the hiring team.' } })
    let rejectDeletion!: (reason: Error) => void
    mock.remove.mockReturnValue(new Promise((_resolve, reject) => { rejectDeletion = reject }))
    renderAt('/espresso/tasks/t1?item=l1')
    await screen.findByRole('heading', { name: 'COO' })
    fireEvent.change(screen.getByLabelText('Your notes'), { target: { value: 'Keep my note' } })
    fireEvent.click(screen.getByRole('button', { name: 'Mark…' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete this search' }))
    await waitFor(() => expect(mock.remove).toHaveBeenCalledWith('t1'))
    expect(screen.getByRole('button', { name: 'Draft email' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Mark…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Redraft' })).toBeDisabled()
    // A menu that was already open can still call its old handler.
    fireEvent.click(screen.getByRole('menuitem', { name: 'Saved' }))
    fireEvent.click(screen.getByRole('button', { name: 'Draft email' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    fireEvent.click(screen.getByRole('button', { name: 'Redraft' }))
    expect(mock.update).not.toHaveBeenCalled()
    expect(mock.email).not.toHaveBeenCalled()
    await act(async () => rejectDeletion(new Error('offline')))
    expect(screen.getByRole('button', { name: 'Draft email' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled()
    expect(screen.getByLabelText('Your notes')).toHaveValue('Keep my note')
  })

  it('retries failed form initialization without losing entered fields', async () => {
    mock.setup.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({
      searches: [], available: true, usage: null,
      consent: { granted: false, disclosure: { version: 'jobs-1', title: 'What Job search shares', body: ['Search terms go to job sites.'] } },
    })
    renderAt()
    fireEvent.click(await screen.findByRole('button', { name: 'New job search…' }))
    const form = await screen.findByRole('dialog', { name: 'New job search' })
    fireEvent.change(within(form).getByLabelText('What are you looking for?'), { target: { value: 'COO roles in Austin' } })
    fireEvent.change(within(form).getByLabelText('Titles (optional)'), { target: { value: 'COO' } })
    expect(await within(form).findByRole('alert')).toHaveTextContent("Couldn't load job search setup.")
    expect(within(form).getByRole('button', { name: 'Start search' })).toBeDisabled()
    expect(mock.create).not.toHaveBeenCalled()
    fireEvent.click(within(form).getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(within(form).queryByRole('alert')).not.toBeInTheDocument())
    expect(within(form).getByLabelText('What are you looking for?')).toHaveValue('COO roles in Austin')
    expect(within(form).getByLabelText('Titles (optional)')).toHaveValue('COO')
    expect(within(form).getByRole('button', { name: 'Start search' })).toBeDisabled()
    fireEvent.click(within(form).getByRole('checkbox', { name: 'I agree' }))
    expect(within(form).getByRole('button', { name: 'Start search' })).toBeEnabled()
    expect(mock.setup).toHaveBeenCalledTimes(2)
    expect(mock.create).not.toHaveBeenCalled()
  })

  it('opens the form in place, only loading setup while mounted', async () => {
    renderAt()
    await screen.findByRole('heading', { name: 'COO roles' })
    expect(mock.setup).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'New job search…' }))
    const form = await screen.findByRole('dialog', { name: 'New job search' })
    await waitFor(() => expect(mock.setup).toHaveBeenCalledTimes(1))
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/tasks/t1')
    fireEvent.click(within(form).getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mock.create).not.toHaveBeenCalled()
  })

  it('resolves the exact task after creation and opens the new search’s pointer task', async () => {
    const created = { ...search, id: 's2', title: 'New search' }
    mock.task.mockImplementation(async (id: string) => id === 't2' ? { ...pointer, id, job_search_id: 's2' } : pointer)
    mock.search.mockImplementation(async (id: string) => id === 's2' ? created : search)
    mock.create.mockImplementation(async () => {
      mock.list.mockResolvedValue({ tasks: [{ ...pointer, id: 't2', job_search_id: 's2' }, pointer] })
      return created
    })
    renderAt()
    fireEvent.click(await screen.findByRole('button', { name: 'New job search…' }))
    const form = await screen.findByRole('dialog', { name: 'New job search' })
    await act(async () => {})
    fireEvent.change(within(form).getByLabelText('What are you looking for?'), { target: { value: 'COO roles in Austin' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Start search' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/espresso/tasks/t2'))
    expect(await screen.findByRole('heading', { name: 'New search' })).toBeInTheDocument()
    expect(mock.lookup).toHaveBeenCalledWith('s2')
    expect(mock.create).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    // Straight to the task, not through the old search link: Tasks stays mounted.
    expect(mock.list).toHaveBeenCalledTimes(1)
    expect(screen.getAllByRole('button', { name: /My job search/ })).toHaveLength(2) // t2 joined t1
  })

  it('keeps an older search opened from a link listed, without re-reading it, across list refreshes', async () => {
    vi.useFakeTimers()
    const recent = { ...pointer, id: 't9', job_search_id: 's9', title: 'Recent search', created_at: '2026-10-17T00:00:00+00:00' }
    mock.list.mockResolvedValue({ tasks: [recent], next_cursor: 'older' })
    renderAt()
    await act(async () => {})
    expect(screen.getByRole('button', { name: /My job search/ })).toBeInTheDocument()
    await act(async () => { await vi.advanceTimersByTimeAsync(35_000) })
    expect(mock.list).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('button', { name: /My job search/ })).toBeInTheDocument()
    expect(mock.task).toHaveBeenCalledTimes(1)
  })

  it('offers a New job search action in the job-only empty state', async () => {
    mock.tasksEnabled = false
    mock.list.mockResolvedValue({ tasks: [] })
    renderAt('/espresso/tasks')
    await screen.findByText('Start a job search')
    const main = screen.getByRole('main')
    fireEvent.click(within(main).getByRole('button', { name: 'New job search' }))
    expect(await screen.findByRole('dialog', { name: 'New job search' })).toBeInTheDocument()
  })

  it('hands a job to Ask Espresso with the job-search prompt', async () => {
    renderAt('/espresso/tasks/t1?item=l1')
    const heading = await screen.findByRole('heading', { name: 'COO' })
    const pane = heading.closest('aside')!
    fireEvent.click(within(pane).getByRole('button', { name: 'Ask Espresso' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/assistant')
    expect(screen.getByTestId('location')).toHaveTextContent('s1')
    expect(screen.getByTestId('location')).toHaveTextContent('l1')
  })
})
