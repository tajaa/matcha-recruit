import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useState } from 'react'
import AssistantSessions from './AssistantSessions'
import { useAssistantSessions } from '../../hooks/useAssistantSessions'
import { ApiError } from '../../../api/client'
import type { AssistantConversation } from '../../api/matchaWork/assistant'

const mock = vi.hoisted(() => ({
  list: vi.fn(), create: vi.fn(), rename: vi.fn(), archive: vi.fn(), restore: vi.fn(),
}))
vi.mock('../../api/matchaWork/assistant', () => ({
  listAssistantConversations: mock.list,
  createAssistantConversation: mock.create,
  renameAssistantConversation: mock.rename,
  archiveAssistantConversation: mock.archive,
  restoreAssistantConversation: mock.restore,
}))

function session(over: Partial<AssistantConversation>): AssistantConversation {
  return { id: 'c1', title: 'Apartment hunt', updated_at: '2026-10-18T10:00:00+00:00', archived: false, main: false, ...over }
}

const main = session({ id: 'main', title: 'Espresso', main: true, updated_at: '2026-10-17T10:00:00+00:00' })
const flights = session({ id: 'c2', title: 'Flights to LA', updated_at: '2026-10-16T10:00:00+00:00' })

function Harness({ initial = 'c1', onSelect = () => {} }: { initial?: string; onSelect?: (id: string) => void }) {
  const sessions = useAssistantSessions()
  const [active, setActive] = useState(initial)
  return <AssistantSessions sessions={sessions} activeId={active} onSelect={(id) => { setActive(id); onSelect(id) }} />
}

function page(items: AssistantConversation[], hasMore = false) {
  return { conversations: items, has_more: hasMore }
}

beforeEach(() => {
  mock.list.mockImplementation((_offset: number, archived: boolean) =>
    Promise.resolve(archived ? page([session({ id: 'old', title: 'Old trip', archived: true })]) : page([session({}), main, flights])))
})

describe('AssistantSessions', () => {
  it('lists the sessions, marks the open one, and filters by name', async () => {
    render(<Harness />)
    const open = await screen.findByRole('button', { name: 'Apartment hunt' })
    expect(open.getAttribute('aria-current')).toBe('page')
    expect(mock.list).toHaveBeenCalledWith(0, false)
    fireEvent.change(screen.getByLabelText('Filter sessions'), { target: { value: 'flight' } })
    expect(screen.queryByRole('button', { name: 'Apartment hunt' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Flights to LA' })).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Filter sessions'), { target: { value: 'zzz' } })
    expect(screen.getByText('No matching sessions')).toBeTruthy()
  })

  it('starts a named session with one request id, even when retried, and opens it', async () => {
    const onSelect = vi.fn()
    mock.create.mockRejectedValueOnce(new ApiError('down', 500, { detail: 'Try again shortly.' }))
    mock.create.mockResolvedValueOnce({ channel_id: 'c9' })
    render(<Harness onSelect={onSelect} />)
    await screen.findByRole('button', { name: 'Apartment hunt' })
    fireEvent.click(screen.getByRole('button', { name: /New session/ }))
    const name = screen.getByLabelText('Name the new session')
    expect((screen.getByRole('button', { name: 'Start session' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(name, { target: { value: '  Taxes  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start session' }))
    expect((await screen.findByRole('alert')).textContent).toBe('Try again shortly.')
    fireEvent.click(screen.getByRole('button', { name: 'Start session' }))
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith('c9'))
    const [first, second] = mock.create.mock.calls
    expect(first[0]).toBe('Taxes')
    expect(second[1]).toBe(first[1])
    expect(mock.list).toHaveBeenLastCalledWith(0, false)
  })

  it('renames in place and skips a save when nothing changed', async () => {
    mock.rename.mockResolvedValue(session({ title: 'Rentals' }))
    render(<Harness />)
    await screen.findByRole('button', { name: 'Apartment hunt' })
    fireEvent.click(screen.getByRole('button', { name: 'Rename Apartment hunt' }))
    fireEvent.blur(screen.getByLabelText('Rename Apartment hunt'))
    expect(mock.rename).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Rename Apartment hunt' }))
    const input = screen.getByLabelText('Rename Apartment hunt')
    fireEvent.change(input, { target: { value: 'Rentals' } })
    fireEvent.submit(input.closest('form')!)
    expect(await screen.findByRole('button', { name: 'Rentals' })).toBeTruthy()
    expect(mock.rename).toHaveBeenCalledWith('c1', 'Rentals')
  })

  it('archives a session (never the main one), moves off it, and restores it from Archived', async () => {
    const onSelect = vi.fn()
    mock.archive.mockResolvedValue(session({ archived: true }))
    mock.restore.mockResolvedValue(session({ id: 'old', title: 'Old trip' }))
    render(<Harness onSelect={onSelect} />)
    await screen.findByRole('button', { name: 'Apartment hunt' })
    expect(screen.queryByRole('button', { name: 'Archive Espresso' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Archive Apartment hunt' }))
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith('main'))
    expect(screen.queryByRole('button', { name: 'Apartment hunt' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Archived sessions/ }))
    const list = await screen.findByRole('list', { name: 'Archived sessions' })
    expect(within(list).getByRole('button', { name: 'Old trip' })).toBeTruthy()
    fireEvent.click(within(list).getByRole('button', { name: 'Restore Old trip' }))
    await waitFor(() => expect(within(list).queryByRole('button', { name: 'Old trip' })).toBeNull())
    fireEvent.click(screen.getByRole('button', { name: /Back to sessions/ }))
    expect(screen.getByRole('button', { name: 'Old trip' })).toBeTruthy()
  })

  it('pages older sessions without duplicates', async () => {
    mock.list.mockImplementation((offset: number) => Promise.resolve(
      offset ? page([flights, session({ id: 'c3', title: 'Groceries' })]) : page([session({}), flights], true)))
    render(<Harness />)
    fireEvent.click(await screen.findByRole('button', { name: 'Load older sessions' }))
    expect(await screen.findByRole('button', { name: 'Groceries' })).toBeTruthy()
    expect(mock.list).toHaveBeenLastCalledWith(2, false)
    expect(screen.getAllByRole('button', { name: 'Flights to LA' })).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Load older sessions' })).toBeNull()
  })
})
