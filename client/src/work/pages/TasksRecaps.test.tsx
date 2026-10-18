import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { WorkSurfaceProvider } from '../routes/WorkSurfaceContext'
import type { RecapDetail, RecapSummary } from '../types'
import Tasks from './Tasks'
import Recap from './Recap'
import Recaps from './Recaps'

const mock = vi.hoisted(() => ({
  list: vi.fn(), recaps: vi.fn(), recap: vi.fn(), remove: vi.fn(), available: true, wide: true,
}))
vi.mock('../../hooks/useMe', () => ({ useMe: () => ({ isPersonal: true, me: { user: { id: 'u1' } } }) }))
vi.mock('../hooks/useEntitlements', () => ({ useEntitlements: () => ({ tasksEnabled: true, jobSearchEnabled: false }) }))
vi.mock('../hooks/useTasksSummary', () => ({ notifyTasksChanged: vi.fn() }))
vi.mock('../hooks/useRecapPreferences', () => ({
  useRecapPreferences: () => (mock.available ? { enabled: true, email_enabled: false, available: true } : null),
}))
vi.mock('../api/matchaWork/agentTasks', () => ({
  getAgentTaskForSearch: vi.fn(), listAgentTasks: mock.list, getAgentTask: vi.fn(), getAgentTaskItem: vi.fn(),
  deleteAgentTask: vi.fn(), getAgentTaskStatus: vi.fn(), updateAgentTaskItem: vi.fn(), startAgentTaskRound: vi.fn(),
  cancelAgentTask: vi.fn(),
}))
vi.mock('../api/matchaWork/recaps', () => ({
  listRecaps: mock.recaps, getRecap: mock.recap, deleteRecap: mock.remove, retryRecap: vi.fn(), getRecapPlayback: vi.fn(),
}))

const summary = (id: string, title: string): RecapSummary => ({
  schema_version: 1, id, title, state: 'rendering', outcome: 'observed', created_at: '2026-10-17T12:00:00Z',
  ready_at: null, expires_at: null, duration_ms: null, can_retry: false, last_error_code: null,
})
const detail = (id: string, title: string): RecapDetail => ({
  ...summary(id, title), chapters: [], source_completed_at: null, sources: [{ kind: 'research', id: 't1' }],
  transcript: [{ schema_version: 1, kind: 'result', title: 'Found 12 apartments', outcome: 'observed', occurred_at: '2026-10-17T12:00:00Z', facts: [{ label: 'Listings', value: '12' }] }],
})

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
          <Route path="/espresso/recaps" element={<Recaps />} />
          <Route path="/espresso/recaps/:recapId" element={<Recap />} />
          <Route path="/espresso/settings" element={<p>Settings</p>} />
        </Routes>
        <Location />
      </WorkSurfaceProvider>
    </MemoryRouter>,
  )
}

const where = () => screen.getByTestId('location').textContent

beforeEach(() => {
  mock.available = true
  mock.wide = true
  vi.stubGlobal('matchMedia', () => ({ matches: mock.wide }))
  localStorage.setItem('espresso-tasks-guide-seen', '1')
  mock.list.mockResolvedValue({ tasks: [], usage: null })
  mock.recaps.mockResolvedValue({ recaps: [summary('r1', 'Apartments in SF'), summary('r2', 'Lip balm')], next_cursor: null })
  mock.recap.mockImplementation((id: string) => Promise.resolve(detail(id, id === 'r1' ? 'Apartments in SF' : 'Lip balm')))
})

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('recaps in Tasks', () => {
  it('switches between Tasks and Recaps, and opens a recap beside the list', async () => {
    renderAt('/espresso/tasks')
    const tabs = await screen.findByRole('tablist', { name: 'Tasks or recaps' })
    expect(within(tabs).getByRole('tab', { name: /Tasks/ }).getAttribute('aria-selected')).toBe('true')
    fireEvent.click(within(tabs).getByRole('tab', { name: /Recaps/ }))
    expect(where()).toBe('/espresso/tasks?view=recaps')
    expect(await screen.findByText('Open a recap on the left')).toBeTruthy()
    fireEvent.click(await screen.findByRole('button', { name: /Apartments in SF/ }))
    expect(where()).toBe('/espresso/tasks?view=recaps&recap=r1')
    expect(await screen.findByRole('heading', { name: 'Apartments in SF' })).toBeTruthy()
    expect(screen.getByText('Your recap is being prepared. You can leave this page.')).toBeTruthy()
    expect(screen.getByText('Found 12 apartments')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Open the task' }).getAttribute('href')).toBe('/espresso/tasks/t1')
    fireEvent.click(screen.getByRole('tab', { name: /Tasks/ }))
    expect(where()).toBe('/espresso/tasks')
  })

  it('narrows to one task’s recaps from its link, and can show all again', async () => {
    renderAt('/espresso/tasks?view=recaps&source_id=t1')
    await screen.findByRole('button', { name: /Apartments in SF/ })
    expect(mock.recaps).toHaveBeenLastCalledWith(null, 't1')
    fireEvent.click(screen.getByRole('button', { name: /Show all/ }))
    expect(where()).toBe('/espresso/tasks?view=recaps')
  })

  it('keeps old /recaps links working, the email’s included', async () => {
    renderAt('/espresso/recaps/r2')
    expect(await screen.findByRole('heading', { name: 'Lip balm' })).toBeTruthy()
    expect(where()).toBe('/espresso/tasks?view=recaps&recap=r2')
    cleanup()
    renderAt('/espresso/recaps?source_id=t9')
    await screen.findByRole('button', { name: /Lip balm/ })
    expect(where()).toBe('/espresso/tasks?view=recaps&source_id=t9')
  })

  it('deletes a recap after confirming and goes back to the list', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mock.remove.mockResolvedValue(undefined)
    renderAt('/espresso/tasks?view=recaps&recap=r1')
    fireEvent.click(await screen.findByRole('button', { name: 'Delete recap' }))
    await screen.findByText('Open a recap on the left')
    expect(mock.remove).toHaveBeenCalledWith('r1')
    expect(where()).toBe('/espresso/tasks?view=recaps')
  })

  it('shows no switch when recaps are not offered, and never auto-opens a task over the recaps view', async () => {
    mock.available = false
    renderAt('/espresso/tasks')
    await screen.findByText(/Give Espresso something to go and do/)
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.getByRole('heading', { name: 'Tasks' })).toBeTruthy()
    cleanup()
    mock.list.mockResolvedValue({ tasks: [{ id: 't1', title: 'A task', status: 'done', items: [] }], usage: null })
    renderAt('/espresso/tasks?view=recaps')
    await screen.findByRole('button', { name: /Apartments in SF/ })
    expect(where()).toBe('/espresso/tasks?view=recaps')
  })
})
