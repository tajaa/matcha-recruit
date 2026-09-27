import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SymChatDetail as Detail } from '../../api/matchaWork/symChat'
import SymChatDetail from './SymChatDetail'

const api = vi.hoisted(() => ({
  getSymChat: vi.fn(),
  sendSymChatMessage: vi.fn(),
  cancelSymChat: vi.fn(),
}))
vi.mock('../../api/matchaWork/symChat', () => api)
vi.mock('../../api/channelSocket', () => ({
  getSharedChannelSocket: () => ({ addSymChatListener: () => {}, removeSymChatListener: () => {} }),
}))

function base(overrides: Partial<Detail> = {}): Detail {
  return {
    id: 'chat-1',
    kind: 'schedule',
    title: 'Planning sync',
    objective: 'Q4 kickoff',
    config: { date: '2026-09-29', window_start: '13:00', window_end: '18:00', duration_min: 30, timezone: 'America/Los_Angeles' },
    status: 'open',
    shape: {
      kind: 'schedule', date: '2026-09-29', timezone: 'America/Los_Angeles', duration_min: 30,
      total: 3, responded: 2,
      best: { start: '14:00', end: '14:30', count: 2, preferred: 0 },
      top_slots: [{ start: '14:00', end: '14:30', count: 2, preferred: 0 }],
      consensus: false,
    },
    resolution: null,
    resolved_at: null,
    is_organizer: false,
    created_at: null,
    participants: [
      { user_id: 'u1', name: 'Org', responded: true, is_organizer: true, is_me: false },
      { user_id: 'u2', name: 'Dana', responded: true, is_organizer: false, is_me: true },
      { user_id: 'u3', name: 'Lee', responded: false, is_organizer: false, is_me: false },
    ],
    updates: [{ seq: 1, content: 'So far 2:00 PM looks best — 2 of 3 can make it (2/3 responded).', created_at: null }],
    messages: [{ id: 'm1', role: 'user', content: 'free after 2', created_at: null }],
    my_stance: null,
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/work/sym-chat/chat-1']}>
      <Routes>
        <Route path="/work/sym-chat/:chatId" element={<SymChatDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.getSymChat.mockReset()
  api.sendSymChatMessage.mockReset()
})

describe('SymChatDetail', () => {
  it('renders the shape, the shared feed, the roll call and my private tunnel', async () => {
    api.getSymChat.mockResolvedValue(base())
    renderPage()
    expect(await screen.findByText('Planning sync')).toBeInTheDocument()
    expect(screen.getByText('2:00 PM–2:30 PM')).toBeInTheDocument()
    expect(screen.getByText('2/3 responded')).toBeInTheDocument()
    expect(screen.getByText(/So far 2:00 PM looks best/)).toBeInTheDocument()
    expect(screen.getByText('Only you and the assistant see this')).toBeInTheDocument()
    expect(screen.getByText('free after 2')).toBeInTheDocument()
    expect(screen.getByText('You')).toBeInTheDocument()
    // Not the organizer → no cancel control.
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
  })

  it('sends from the tunnel input', async () => {
    api.getSymChat.mockResolvedValue(base())
    api.sendSymChatMessage.mockResolvedValue({ reply: 'ok', error: false, status: 'open', shape: {}, resolved: false })
    renderPage()
    const input = await screen.findByLabelText('Message the assistant')
    fireEvent.change(input, { target: { value: 'not 3:30' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(api.sendSymChatMessage).toHaveBeenCalledWith('chat-1', 'not 3:30'))
  })

  it('shows the settled outcome and locks the tunnel once resolved', async () => {
    api.getSymChat.mockResolvedValue(base({
      status: 'resolved',
      resolution: { kind: 'schedule', date: '2026-09-29', start: '14:00', end: '14:30', timezone: 'America/Los_Angeles' },
    }))
    renderPage()
    expect(await screen.findByText(/2:00 PM–2:30 PM on Tue, Sep 29/)).toBeInTheDocument()
    expect(screen.getByLabelText('Message the assistant')).toBeDisabled()
    expect(screen.getByText('Settled')).toBeInTheDocument()
  })

  it('renders decide options with vetoes', async () => {
    api.getSymChat.mockResolvedValue(base({
      kind: 'decide',
      config: { options: ['Thai Palace'] },
      shape: {
        kind: 'decide', total: 2, responded: 2,
        options: [{ name: 'Thai Palace', ok: 1, top: 0, vetoes: 1 }, { name: 'Burger Barn', ok: 2, top: 1, vetoes: 0 }],
        leading: { name: 'Burger Barn', ok: 2, top: 1, vetoes: 0 },
        consensus: false,
      },
    }))
    renderPage()
    expect(await screen.findByText('Burger Barn')).toBeInTheDocument()
    expect(screen.getByText(/1 veto/)).toBeInTheDocument()
  })

  it('shows the error with a way back when the chat is not visible', async () => {
    api.getSymChat.mockRejectedValue(new Error('Sym-chat not found'))
    renderPage()
    expect(await screen.findByText('Sym-chat not found')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to sym-chats' })).toHaveAttribute('href', '/work/sym-chat')
  })
})
