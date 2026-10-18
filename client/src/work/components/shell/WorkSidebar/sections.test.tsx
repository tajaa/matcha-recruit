import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import type { ChannelSummary } from '../../../api/channels'
import type { MWProject, MWThread } from '../../../types'
import ChannelsSection from './ChannelsSection'
import ChatsSection from './ChatsSection'
import ProjectsSection from './ProjectsSection'
import type { SidebarRename } from './useSidebarRename'

vi.mock('../../../hooks/useStars', () => ({ useStars: () => [], toggleStar: vi.fn() }))

const rename = { renaming: null, startRename: vi.fn() } as unknown as SidebarRename
const channel = (n: number, unread = 0) =>
  ({ id: `c${n}`, name: `Channel ${n}`, unread_count: unread, is_paid: false }) as ChannelSummary

function channels(list: ChannelSummary[], over: Partial<React.ComponentProps<typeof ChannelsSection>> = {}) {
  const props: React.ComponentProps<typeof ChannelsSection> = {
    channels: list, channelsOpen: true, onToggle: vi.fn(), filter: '', totalChannelUnread: 0, canCreate: true,
    base: '/espresso', navigate: vi.fn(), isActive: () => false, setShowCreateChannel: vi.fn(), rename, ...over,
  }
  return render(<ChannelsSection {...props} />)
}

const names = () => screen.queryAllByText(/^Channel \d+$/).map((el) => el.textContent)

describe('ChannelsSection', () => {
  it('shows the first 8, keeps unread and open channels, and expands in place', () => {
    const list = Array.from({ length: 14 }, (_, i) => channel(i + 1, i === 11 ? 3 : 0))
    channels(list, { isActive: (path) => path === '/espresso/channels/c13' })
    expect(names()).toEqual(['Channel 1', 'Channel 2', 'Channel 3', 'Channel 4', 'Channel 5', 'Channel 6', 'Channel 7', 'Channel 8', 'Channel 12', 'Channel 13'])
    expect(screen.getByLabelText('3 unread')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Show 4 more' }))
    expect(names()).toHaveLength(14)
    fireEvent.click(screen.getByRole('button', { name: 'Show less' }))
    expect(names()).toHaveLength(10)
  })

  it('shows every match while filtering, with no cap row', () => {
    channels(Array.from({ length: 12 }, (_, i) => channel(i + 1)), { filter: 'channel 1' })
    expect(names()).toEqual(['Channel 1', 'Channel 10', 'Channel 11', 'Channel 12'])
    expect(screen.queryByRole('button', { name: /Show \d+ more/ })).toBeNull()
  })

  it('folds with the unread total showing, and has labelled actions', () => {
    const onToggle = vi.fn()
    const navigate = vi.fn()
    const setShowCreateChannel = vi.fn()
    channels([channel(1, 2)], { channelsOpen: false, totalChannelUnread: 2, onToggle, navigate, setShowCreateChannel })
    const header = screen.getByRole('button', { name: /Channels/ })
    expect(header.getAttribute('aria-expanded')).toBe('false')
    expect(within(header).getByLabelText('2 unread')).toBeTruthy()
    expect(names()).toEqual([])
    fireEvent.click(header)
    expect(onToggle).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Browse channels' }))
    expect(navigate).toHaveBeenCalledWith('/espresso/channels')
    fireEvent.click(screen.getByRole('button', { name: 'New channel' }))
    expect(setShowCreateChannel).toHaveBeenCalledWith(true)
  })

  it('says when there are none, and offers no New channel to someone who can’t make one', () => {
    channels([], { canCreate: false })
    expect(screen.getByText('No channels yet')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'New channel' })).toBeNull()
  })
})

describe('ChatsSection', () => {
  const thread = (n: number) => ({ id: `t${n}`, title: `Chat ${n}`, collaborator_count: 0, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z' }) as MWThread
  it('shows 5, then up to 20, then links to all chats', () => {
    const navigate = vi.fn()
    render(
      <MemoryRouter>
        <ChatsSection threads={Array.from({ length: 25 }, (_, i) => thread(i + 1))} chatsOpen onToggle={vi.fn()} onNewChat={vi.fn()}
          filter="" base="/espresso" navigate={navigate} isActive={() => false} rename={rename} onArchive={vi.fn()} />
      </MemoryRouter>,
    )
    expect(screen.getAllByRole('link')).toHaveLength(5)
    fireEvent.click(screen.getByRole('button', { name: 'Show 15 more' }))
    expect(screen.getAllByRole('link')).toHaveLength(20)
    fireEvent.click(screen.getByRole('button', { name: 'All chats (25)' }))
    expect(navigate).toHaveBeenCalledWith('/espresso')
  })
})

describe('ProjectsSection', () => {
  const project = (n: number, client?: string) =>
    ({ id: `p${n}`, title: `Workspace ${n}`, hiring_client_id: client ?? null, hiring_client_name: client ? `Client ${client}` : null }) as MWProject
  const projects = (list: MWProject[]) => render(
    <ProjectsSection projects={list} projectsOpen onToggle={vi.fn()} filter="" isPersonal base="/espresso"
      navigate={vi.fn()} isActive={() => false} setShowProjectTypePicker={vi.fn()} rename={rename} />,
  )

  it('shows no group heading when everything is in one group, and caps at 8', () => {
    projects(Array.from({ length: 10 }, (_, i) => project(i + 1)))
    expect(screen.queryByText('Unassigned')).toBeNull()
    expect(screen.getAllByText(/^Workspace \d+$/)).toHaveLength(8)
    expect(screen.getByRole('button', { name: 'Show 2 more' })).toBeTruthy()
  })

  it('groups by hiring client when there is more than one, unassigned last', () => {
    projects([project(1), project(2, 'b'), project(3, 'a')])
    const headings = screen.getAllByText(/^(Client \w|Unassigned)$/).map((el) => el.textContent)
    expect(headings).toEqual(['Client a', 'Client b', 'Unassigned'])
  })
})
