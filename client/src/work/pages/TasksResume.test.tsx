import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { resetAuthCaches } from '../../api/authReset'
import { WorkSurfaceProvider } from '../routes/WorkSurfaceContext'
import Tasks from './Tasks'

const mock = vi.hoisted(() => ({ list: vi.fn(), resume: vi.fn(), jobs: true }))
vi.mock('../../hooks/useMe', () => ({ useMe: () => ({ isPersonal: true, me: { user: { id: 'u1' } } }) }))
vi.mock('../hooks/useEntitlements', () => ({ useEntitlements: () => ({ tasksEnabled: true, jobSearchEnabled: mock.jobs }) }))
vi.mock('../hooks/useTasksSummary', () => ({ notifyTasksChanged: vi.fn() }))
vi.mock('../hooks/useRecapPreferences', () => ({ useRecapPreferences: () => null }))
vi.mock('../api/matchaWork/agentTasks', () => ({
  getAgentTaskForSearch: vi.fn(), listAgentTasks: mock.list, getAgentTask: () => new Promise(() => {}), getAgentTaskItem: vi.fn(),
  deleteAgentTask: vi.fn(), getAgentTaskStatus: vi.fn(), updateAgentTaskItem: vi.fn(), startAgentTaskRound: vi.fn(),
  cancelAgentTask: vi.fn(),
}))
vi.mock('../../api/profileResume', () => ({
  getMyResume: mock.resume, uploadMyResume: vi.fn(), updateMyResumeText: vi.fn(), deleteMyResume: vi.fn(),
}))

function Location() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <WorkSurfaceProvider value="espresso">
        <Routes>
          <Route path="/espresso/tasks" element={<Tasks />} />
          <Route path="/espresso/tasks/:taskId" element={<Tasks />} />
        </Routes>
        <Location />
      </WorkSurfaceProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  resetAuthCaches()
  mock.jobs = true
  vi.stubGlobal('matchMedia', () => ({ matches: true }))
  localStorage.setItem('espresso-tasks-guide-seen', '1')
  mock.list.mockResolvedValue({ tasks: [{ id: 't1', title: 'A task', status: 'done', items: [] }], usage: null })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('the résumé in Tasks', () => {
  it('has a row that opens the résumé beside the list, without opening a task over it', async () => {
    mock.resume.mockResolvedValue(null)
    renderAt('/espresso/tasks?view=resume')
    expect(await screen.findByRole('heading', { name: 'Your résumé' })).toBeTruthy()
    expect(await screen.findByText('Drop your résumé here, or choose a file')).toBeTruthy()
    expect(screen.getByTestId('location').textContent).toBe('/espresso/tasks?view=resume')
    expect(screen.getByRole('button', { name: /Add your résumé/ }).getAttribute('aria-current')).toBe('page')
  })

  it('names the saved résumé in the row', async () => {
    mock.resume.mockResolvedValue({ filename: 'Haley-Rivera-Resume.pdf', resume_url: '', parsed_data: {}, updated_at: '2026-10-18T00:00:00Z', text: 'x'.repeat(60) })
    renderAt('/espresso/tasks/t1')
    fireEvent.click(await screen.findByRole('button', { name: /Résumé · Haley-Rivera-Resume\.pdf/ }))
    expect(screen.getByTestId('location').textContent).toBe('/espresso/tasks?view=resume')
    expect(await screen.findByLabelText('The text Espresso uses')).toBeTruthy()
  })

  it('shows no row to an account without job search', async () => {
    mock.jobs = false
    mock.resume.mockResolvedValue(null)
    renderAt('/espresso/tasks')
    await screen.findByText('A task')
    expect(screen.queryByRole('button', { name: /résumé/i })).toBeNull()
    expect(mock.resume).not.toHaveBeenCalled()
  })
})
