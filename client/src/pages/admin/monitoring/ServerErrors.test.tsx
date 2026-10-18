import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../../api/client'
import ServerErrors from './ServerErrors'

vi.mock('../../../api/client', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
const report = {
  id: 'error-1', fingerprint: 'fingerprint-1', kind: 'exception', level: 'ERROR', logger_name: 'api', message: 'Test failure',
  exception_type: 'ValueError', traceback: 'Test traceback', source: 'api', hostname: 'test-host', request_method: 'GET', request_path: '/api/test', request_status: 500,
  user_id: 'user-1', user_email: 'admin@example.com', context: { request_id: 'request-1' }, occurrences: 2,
  first_seen: '2026-01-01T00:00:00Z', last_seen: '2026-01-01T00:00:00Z', resolved_at: null as string | null,
}

beforeEach(() => { vi.clearAllMocks() })

describe('server errors in the shared console', () => {
  it('copies the full report and preserves resolve, reload, and reopen actions', async () => {
    let resolved: string | null = null
    vi.mocked(api.get).mockImplementation(async (path) => path.includes('/stats')
      ? { by_kind: [{ kind: 'exception', count: 1, occurrences: 2 }], by_source: [], top: [] }
      : { total: 1, items: [{ ...report, resolved_at: resolved }] })
    vi.mocked(api.post).mockImplementation(async (path) => { resolved = path.endsWith('/unresolve') ? null : '2026-01-02T00:00:00Z' })
    const user = userEvent.setup(), copy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    render(<ServerErrors />)
    await screen.findByText('Test failure')
    await user.click(screen.getByRole('button', { expanded: false }))
    expect(screen.getByText('Test traceback')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Copy report' }))
    expect(copy).toHaveBeenCalledWith(expect.stringContaining('Fingerprint: fingerprint-1'))
    expect(copy).toHaveBeenCalledWith(expect.stringContaining('request-1'))
    await user.click(screen.getByRole('button', { name: 'Mark resolved' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/admin/server-errors/error-1/resolve', {}))
    await user.click(await screen.findByRole('button', { name: 'Mark unresolved' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/admin/server-errors/error-1/unresolve', {}))
  })

  it('keeps source, time-window, and resolution filters in the API request', async () => {
    vi.mocked(api.get).mockImplementation(async (path) => path.includes('/stats') ? { by_kind: [], by_source: [], top: [] } : { total: 0, items: [] })
    const user = userEvent.setup()
    render(<ServerErrors />)
    await screen.findByText('No errors in the selected window.')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Error source' }), 'celery')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Error time window' }), '168')
    await user.click(screen.getByRole('checkbox', { name: 'Show resolved' }))
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/admin/server-errors?source=celery&resolved=true&since_hours=168&limit=100'))
  })
})
