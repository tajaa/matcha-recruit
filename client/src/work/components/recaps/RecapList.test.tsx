import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import RecapList from './RecapList'
import type { RecapSummary } from '../../types'

const mock = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock('../../api/matchaWork/recaps', () => ({ listRecaps: mock.list }))
const item = (title: string, over: Partial<RecapSummary> = {}) =>
  ({ id: title, title, state: 'ready', created_at: '2026-10-17T12:00:00Z', duration_ms: 70_000, ...over }) as RecapSummary

function List({ owner = 'owner-a', source = null as string | null, selectedId = null as string | null, onOpen = vi.fn() }) {
  return <RecapList owner={owner} source={source} selectedId={selectedId} onOpen={onOpen} />
}

beforeEach(() => { vi.clearAllMocks() })
describe('recap list', () => {
  it('says what state each recap is in and opens one', async () => {
    const onOpen = vi.fn()
    mock.list.mockResolvedValue({ recaps: [item('Apartments'), item('Lip balm', { state: 'rendering', duration_ms: null })], next_cursor: null })
    render(<List onOpen={onOpen} selectedId="Apartments" />)
    const open = await screen.findByRole('button', { name: /Apartments/ })
    expect(open.getAttribute('aria-current')).toBe('page')
    expect(open.textContent).toContain('Ready')
    expect(open.textContent).toContain('70s')
    expect(screen.getByRole('button', { name: /Lip balm/ }).textContent).toContain('Being prepared')
    fireEvent.click(screen.getByRole('button', { name: /Lip balm/ }))
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 'Lip balm' }))
  })

  it('resets the cursor when switching source filters', async () => {
    mock.list.mockResolvedValueOnce({ recaps: [item('Recent')], next_cursor: 'older' })
      .mockResolvedValueOnce({ recaps: [item('Older')], next_cursor: null })
      .mockResolvedValue({ recaps: [item('New task recap')], next_cursor: null })
    const view = render(<List />)
    fireEvent.click(await screen.findByText('Load older recaps'))
    await screen.findByText('Older')
    expect(mock.list).toHaveBeenLastCalledWith('older', null)
    view.rerender(<List source="new-task" />)
    await screen.findByText('New task recap')
    expect(mock.list).toHaveBeenLastCalledWith(null, 'new-task')
    expect(screen.queryByText('Older')).toBeNull()
    mock.list.mockResolvedValue({ recaps: [], next_cursor: null })
    view.rerender(<List source="empty" />)
    expect(await screen.findByText('No recaps for this task.')).toBeTruthy()
  })

  it('does not reuse another account’s page or cursor', async () => {
    mock.list.mockResolvedValueOnce({ recaps: [item('Private A')], next_cursor: 'older' })
      .mockResolvedValueOnce({ recaps: [item('Old A')], next_cursor: null })
      .mockResolvedValue({ recaps: [item('Private B')], next_cursor: null })
    const view = render(<List />)
    fireEvent.click(await screen.findByText('Load older recaps'))
    await screen.findByText('Old A')
    view.rerender(<List owner="owner-b" />)
    await screen.findByText('Private B')
    await waitFor(() => expect(mock.list).toHaveBeenLastCalledWith(null, null))
    expect(screen.queryByText('Private A')).toBeNull()
  })

  it('shows a load error', async () => {
    mock.list.mockRejectedValue(new Error('down'))
    render(<List />)
    expect((await screen.findByRole('alert')).textContent).toContain('Could not load recaps')
  })
})
