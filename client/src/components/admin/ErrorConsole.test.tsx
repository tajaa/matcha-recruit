import { AdminButton } from './AdminUI'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ErrorConsole } from './ErrorConsole'

const item = { id: 'e1', kind: 'exception', message: 'Request failed', time: '2026-01-01T00:00:00Z' }
function props() {
  return {
    title: 'Errors', description: 'Investigate reports', loading: false, onRefresh: vi.fn(),
    kinds: [{ key: 'exception', label: 'Exception', color: 'text-red-300', count: 3 }], selectedKind: '', onKindChange: vi.fn(), filters: null,
    items: [item], summary: (row: typeof item) => ({ id: row.id, kind: row.kind, title: row.message, at: row.time }),
    details: () => ({ trace: { label: 'Traceback', value: 'Trace details' }, context: { request_id: 'r1' }, fields: [{ label: 'User agent', value: 'Test browser' }] }), top: [],
  }
}
describe('shared error console', () => {
  it('expands diagnostics and preserves the caller’s copy/resolve actions', async () => {
    const action = vi.fn(), options = props()
    render(<ErrorConsole {...options} details={() => ({ ...options.details(), actions: <AdminButton onClick={action}>Mark resolved</AdminButton> })} />)
    expect(screen.queryByText('Trace details')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { expanded: false }))
    expect(screen.getByText('Trace details')).toBeInTheDocument()
    expect(screen.getByText(/"request_id": "r1"/)).toBeInTheDocument()
    expect(screen.getByText('Test browser')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Mark resolved' }))
    expect(action).toHaveBeenCalledOnce()
    await userEvent.click(screen.getByRole('button', { expanded: true }))
    expect(screen.queryByText('Trace details')).not.toBeInTheDocument()
  })

  it('reports a failed load instead of a successful empty result', () => {
    render(<ErrorConsole {...props()} items={[]} error="Couldn’t load reports" />)
    expect(screen.getByRole('alert')).toHaveTextContent('Couldn’t load reports')
    expect(screen.queryByText('No errors in the selected window.')).not.toBeInTheDocument()
  })

  it('keeps refresh and kind filtering connected to the caller', async () => {
    const options = props()
    render(<ErrorConsole {...options} />)
    await userEvent.click(screen.getByRole('button', { name: 'Refresh' }))
    await userEvent.click(screen.getByRole('button', { name: 'Exception 3' }))
    expect(options.onRefresh).toHaveBeenCalledOnce()
    expect(options.onKindChange).toHaveBeenCalledWith('exception')
  })
})
