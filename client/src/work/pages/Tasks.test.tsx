import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { WorkSurfaceProvider } from '../routes/WorkSurfaceContext'
import type { AgentTaskDetail } from '../types'
import type { JobLeadDetail, JobSearchDetail } from '../api/matchaWork/jobSearch'
import Tasks from './Tasks'

const mock = vi.hoisted(() => ({
  list: vi.fn(), task: vi.fn(), item: vi.fn(), remove: vi.fn(), search: vi.fn(), lead: vi.fn(),
  searches: vi.fn(), create: vi.fn(), update: vi.fn(), email: vi.fn(), status: vi.fn(), taskStatus: vi.fn(),
  tasksEnabled: true, jobSearchEnabled: true, wide: false,
}))
vi.mock('../../hooks/useMe', () => ({ useMe: () => ({ isPersonal: true }) }))
vi.mock('../hooks/useEntitlements', () => ({ useEntitlements: () => mock }))
vi.mock('../hooks/useTasksSummary', () => ({ notifyTasksChanged: vi.fn() }))
vi.mock('../../api/profileResume', () => ({ getMyResume: () => Promise.resolve(null), uploadMyResume: vi.fn() }))
vi.mock('../api/matchaWork/agentTasks', () => ({
  listAgentTasks: mock.list, getAgentTask: mock.task, getAgentTaskItem: mock.item, deleteAgentTask: mock.remove,
  getAgentTaskStatus: mock.taskStatus, updateAgentTaskItem: vi.fn(), startAgentTaskRound: vi.fn(), cancelAgentTask: vi.fn(),
}))
vi.mock('../api/matchaWork/jobSearch', () => ({
  listJobSearches: mock.searches, getJobSearch: mock.search, getJobLead: mock.lead,
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
  mock.searches.mockResolvedValue({ searches: [search], consent: { granted: true }, usage: null, available: true })
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
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000) })
    expect(mock.status).toHaveBeenCalledTimes(1)
    expect(mock.taskStatus).not.toHaveBeenCalled()
    expect(mock.list).toHaveBeenCalledTimes(reads + 1)
    expect(screen.getByRole('button', { name: /My job search/ })).toHaveTextContent('Done')
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

  it('opens the form in place, only loading its list while mounted', async () => {
    renderAt()
    await screen.findByRole('heading', { name: 'COO roles' })
    expect(mock.searches).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'New job search…' }))
    const form = await screen.findByRole('dialog', { name: 'New job search' })
    await waitFor(() => expect(mock.searches).toHaveBeenCalledTimes(1))
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/tasks/t1')
    fireEvent.click(within(form).getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mock.create).not.toHaveBeenCalled()
  })

  it('reloads Tasks after creation and opens the new search’s pointer task', async () => {
    const created = { ...search, id: 's2' }
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
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
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
