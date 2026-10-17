import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import Recaps from './Recaps'
import type { RecapSummary } from '../types'

const mock = vi.hoisted(() => ({ list: vi.fn(), owner: 'owner-a' }))
vi.mock('../api/matchaWork/recaps', () => ({ listRecaps: mock.list }))
vi.mock('../../hooks/useMe', () => ({ useMe: () => ({ me: { user: { id: mock.owner } }, isPersonal: true, loading: false }) }))
vi.mock('../routes/WorkSurfaceContext', () => ({ useWorkBase: () => '/espresso' }))
const item = (title: string) => ({ id: title, title, state: 'ready', created_at: '2026-10-17T12:00:00Z', duration_ms: 70_000 }) as RecapSummary
function Nav() { const navigate = useNavigate(); return <><button onClick={() => navigate('/espresso/recaps?source_id=new-task')}>New source</button><button onClick={() => navigate('/espresso/recaps')}>All sources</button></> }
function Page() { return <MemoryRouter initialEntries={['/espresso/recaps']}><Nav /><Routes><Route path="/espresso/recaps" element={<Recaps />} /></Routes></MemoryRouter> }

beforeEach(() => { vi.clearAllMocks(); mock.owner = 'owner-a' })
describe('recap library', () => {
  it('resets the cursor when switching source filters', async () => {
    mock.list.mockResolvedValueOnce({ recaps: [item('Recent')], next_cursor: 'older' })
      .mockResolvedValueOnce({ recaps: [item('Older')], next_cursor: null })
      .mockResolvedValue({ recaps: [item('New task recap')], next_cursor: null })
    render(<Page />)
    fireEvent.click(await screen.findByText('Load older recaps'))
    await screen.findByText('Older')
    fireEvent.click(screen.getByText('New source'))
    await screen.findByText('New task recap')
    expect(mock.list).toHaveBeenLastCalledWith(null, 'new-task')
    expect(screen.queryByText('Older')).toBeNull()
    mock.list.mockResolvedValue({ recaps: [item('Recent again')], next_cursor: null })
    fireEvent.click(screen.getByText('All sources'))
    await screen.findByText('Recent again')
    expect(mock.list).toHaveBeenLastCalledWith(null, null)
  })
  it('does not reuse another account’s page or cursor', async () => {
    mock.list.mockResolvedValueOnce({ recaps: [item('Private A')], next_cursor: 'older' })
      .mockResolvedValueOnce({ recaps: [item('Old A')], next_cursor: null })
      .mockResolvedValue({ recaps: [item('Private B')], next_cursor: null })
    const view = render(<Page />)
    fireEvent.click(await screen.findByText('Load older recaps'))
    await screen.findByText('Old A')
    mock.owner = 'owner-b'
    view.rerender(<Page />)
    await screen.findByText('Private B')
    await waitFor(() => expect(mock.list).toHaveBeenLastCalledWith(null, null))
    expect(screen.queryByText('Private A')).toBeNull()
    mock.list.mockResolvedValue({ recaps: [item('Recent A again')], next_cursor: null })
    mock.owner = 'owner-a'
    view.rerender(<Page />)
    await screen.findByText('Recent A again')
    expect(mock.list).toHaveBeenLastCalledWith(null, null)
  })
})
