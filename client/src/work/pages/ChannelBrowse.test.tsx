import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import ChannelBrowse from './ChannelBrowse'
import { WorkSurfaceProvider } from '../routes/WorkSurfaceContext'

const channelApi = vi.hoisted(() => ({
  listChannels: vi.fn(),
  discoverChannels: vi.fn(),
  joinChannel: vi.fn(),
  createChannelCheckout: vi.fn(),
}))

vi.mock('../api/channels', () => channelApi)
vi.mock('../../hooks/useMe', () => ({
  useMe: () => ({ me: { user: { role: 'individual' } } }),
}))
vi.mock('../components/channels/CreateChannelModal', () => ({ default: () => null }))

const joinedChannel = {
  id: 'joined',
  name: 'Joined channel',
  slug: 'joined-channel',
  description: null,
  visibility: 'public',
  member_count: 1,
  unread_count: 0,
  last_message_at: null,
  last_message_preview: null,
  is_member: true,
}

const discoverableChannel = {
  ...joinedChannel,
  id: 'discoverable',
  name: 'Discoverable channel',
  slug: 'discoverable-channel',
  is_member: false,
}

beforeEach(() => {
  vi.clearAllMocks()
  channelApi.listChannels.mockResolvedValue([joinedChannel])
  channelApi.discoverChannels.mockResolvedValue([discoverableChannel])
})

describe('ChannelBrowse', () => {
  it('keeps Discover results visible when the active tab is clicked again', async () => {
    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <WorkSurfaceProvider value="espresso">
          <ChannelBrowse />
        </WorkSurfaceProvider>
      </MemoryRouter>,
    )

    const discoverTab = screen.getByRole('button', { name: 'Discover' })
    await user.click(discoverTab)

    expect(await screen.findByText('Discoverable channel')).toBeInTheDocument()
    expect(channelApi.discoverChannels).toHaveBeenCalledTimes(1)

    await user.click(discoverTab)

    expect(screen.getByText('Discoverable channel')).toBeInTheDocument()
    await waitFor(() => expect(channelApi.discoverChannels).toHaveBeenCalledTimes(1))
  })
})
