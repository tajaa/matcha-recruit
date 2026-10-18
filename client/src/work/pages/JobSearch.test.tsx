import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { WorkSurfaceProvider } from '../routes/WorkSurfaceContext'
import JobSearchRedirect from './JobSearch'
import { ApiError } from '../../api/client'

const mock = vi.hoisted(() => ({ lookup: vi.fn(), list: vi.fn(), personal: true, loading: false }))
vi.mock('../api/matchaWork/agentTasks', () => ({ getAgentTaskForSearch: mock.lookup, listAgentTasks: mock.list }))
vi.mock('../../hooks/useMe', () => ({ useMe: () => ({ isPersonal: mock.personal, loading: mock.loading }) }))

function Location() {
  const location = useLocation()
  const navigate = useNavigate()
  return <>
    <output data-testid="location">{location.pathname}{location.search}</output>
    <button onClick={() => navigate(-1)}>Back</button>
    <button onClick={() => navigate('/espresso/jobs/s2?job=l2')}>Other search</button>
  </>
}

function TestApp({ path }: { path: string }) {
  return (
    <MemoryRouter initialEntries={['/espresso/email', path]} initialIndex={1}>
      <WorkSurfaceProvider value="espresso">
        <Routes>
          <Route path="/espresso/jobs" element={<JobSearchRedirect />} />
          <Route path="/espresso/jobs/:searchId" element={<JobSearchRedirect />} />
          <Route path="*" element={null} />
        </Routes>
        <Location />
      </WorkSurfaceProvider>
    </MemoryRouter>
  )
}

function renderAt(path: string) {
  return render(<TestApp path={path} />)
}

beforeEach(() => {
  mock.personal = true
  mock.loading = false
  mock.lookup.mockImplementation(async (searchId: string) => ({
    id: searchId === 's1' ? 't1' : 't2', engine: 'job_search', job_search_id: searchId, status: 'done',
  }))
})

describe('old Job search URLs', () => {
  it('replaces /jobs with Tasks without loading searches or tasks', async () => {
    renderAt('/espresso/jobs')
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/espresso/tasks'))
    expect(mock.lookup).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('Back'))
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/email')
  })

  it('resolves the pointer task and converts job to item, preserving encoding', async () => {
    renderAt('/espresso/jobs/s1?job=lead%2Fone%20%26two')
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/espresso/tasks/t1?item=lead%2Fone%20%26two'))
    expect(mock.lookup).toHaveBeenCalledWith('s1')
    fireEvent.click(screen.getByText('Back'))
    expect(screen.getByTestId('location')).toHaveTextContent('/espresso/email')
  })

  it('opens the task without a job parameter', async () => {
    renderAt('/espresso/jobs/s1')
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/espresso/tasks/t1'))
  })

  it('resolves an older search even with 50 newer tasks outside its history window', async () => {
    mock.list.mockResolvedValue({ tasks: Array.from({ length: 50 }, (_, index) => ({
      id: `new-${index}`, engine: index % 2 ? 'chain' : 'job_search', job_search_id: `s-new-${index}`, status: 'done',
    })) })
    renderAt('/espresso/jobs/s1?job=l1')
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/espresso/tasks/t1?item=l1'))
    expect(mock.lookup).toHaveBeenCalledWith('s1')
    expect(mock.list).not.toHaveBeenCalled()
  })

  it('waits for identity on a fresh page load instead of dropping the search and job', async () => {
    mock.personal = false
    mock.loading = true
    const view = renderAt('/espresso/jobs/s1?job=l1')
    expect(screen.getByTestId('location').textContent).toBe('/espresso/jobs/s1?job=l1')
    expect(mock.lookup).not.toHaveBeenCalled()
    mock.personal = true
    mock.loading = false
    view.rerender(<TestApp path="/espresso/jobs/s1?job=l1" />)
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/espresso/tasks/t1?item=l1'))
  })

  it.each(['missing', 'unavailable'])('falls back to Tasks when the task is %s', async (reason) => {
    mock.lookup.mockRejectedValue(reason === 'missing' ? new ApiError('Job search not found.', 404, {}) : new Error('offline'))
    renderAt('/espresso/jobs/s1?job=l1')
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/espresso/tasks'))
  })

  it('ignores an older lookup after another search is opened', async () => {
    let finish!: (value: { id: string }) => void
    mock.lookup.mockReturnValueOnce(new Promise((resolve) => { finish = resolve }))
    renderAt('/espresso/jobs/s1?job=l1')
    fireEvent.click(screen.getByText('Other search'))
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/espresso/tasks/t2?item=l2'))
    await act(async () => finish({ id: 't1' }))
    expect(screen.getByTestId('location').textContent).toBe('/espresso/tasks/t2?item=l2')
  })
})
