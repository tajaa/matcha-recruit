import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getSharedChannelSocket } from '../api/channelSocket'
import { getBroadcastStatus, getBroadcastToken, refreshBroadcastToken } from '../api/channelBroadcasts'
import { useLiveKitBroadcast } from './useLiveKitBroadcast'

const media = vi.hoisted(() => ({
  rooms: [] as unknown[],
  socket: {
    onBroadcastStarted: null,
    onBroadcastEnded: null,
    onBroadcastPublisherChanged: null,
    onBroadcastTokenGrant: null,
  },
}))

vi.mock('livekit-client', () => {
  class FakeRoom {
    remoteParticipants = new Map()
    localParticipant = {
      trackPublications: new Map(),
      setMicrophoneEnabled: vi.fn(async () => {}),
      setCameraEnabled: vi.fn(async () => {}),
    }
    connect = vi.fn(async () => {})
    disconnect = vi.fn(async () => {})
    on = vi.fn()
    removeAllListeners = vi.fn()
    constructor() { media.rooms.push(this) }
  }
  return { Room: FakeRoom, RoomEvent: {
    TrackSubscribed: 'subscribed', TrackUnsubscribed: 'unsubscribed',
    ParticipantConnected: 'joined', ParticipantDisconnected: 'left',
    LocalTrackPublished: 'published', LocalTrackUnpublished: 'unpublished',
    Disconnected: 'disconnected',
  }, Track: { Kind: { Video: 'video' } },
  DisconnectReason: { CLIENT_INITIATED: 1, DUPLICATE_IDENTITY: 2, SERVER_SHUTDOWN: 3, PARTICIPANT_REMOVED: 4, ROOM_DELETED: 5 } }
})

vi.mock('../api/channelSocket', () => ({
  getSharedChannelSocket: vi.fn(() => media.socket),
}))
vi.mock('../api/channelBroadcasts', () => ({
  getBroadcastStatus: vi.fn(), getBroadcastToken: vi.fn(),
  refreshBroadcastToken: vi.fn(), setBroadcastPublisher: vi.fn(),
  startBroadcast: vi.fn(), stopBroadcast: vi.fn(),
}))

const active = {
  active: true, broadcast_id: 'bc-1', started_by: 'owner',
  publisher_user_ids: ['owner'], max_duration_seconds: 600,
  weekly_limit: 10, weekly_used: 1, weekly_remaining: 9,
}

type FakeRoom = { disconnect: ReturnType<typeof vi.fn>; on: ReturnType<typeof vi.fn>; localParticipant: {
  setMicrophoneEnabled: ReturnType<typeof vi.fn>
} }

describe('broadcast lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    media.rooms.length = 0
    vi.mocked(getBroadcastStatus).mockResolvedValue(active)
    vi.mocked(getBroadcastToken).mockResolvedValue({
      token: 'viewer', livekit_url: 'ws://livekit', room: 'channel-test',
      max_duration_seconds: 600, can_publish: false,
    })
  })

  it('tears down once when ended arrives twice', async () => {
    const { result } = renderHook(() => useLiveKitBroadcast('channel', 'viewer', []))
    await waitFor(() => expect(result.current.status?.active).toBe(true))
    await act(async () => { await result.current.watch() })
    expect(result.current.connectionState).toBe('connected')
    const room = media.rooms[0] as FakeRoom
    const socket = getSharedChannelSocket()
    act(() => {
      socket.onBroadcastEnded?.({ channel_id: 'channel', broadcast_id: 'bc-1' })
      socket.onBroadcastEnded?.({ channel_id: 'channel', broadcast_id: 'bc-1' })
    })
    expect(room.disconnect).toHaveBeenCalledTimes(1)
    expect(result.current.connectionState).toBe('idle')
  })

  it('reconnects with the granted publisher token and enables the microphone', async () => {
    const { result } = renderHook(() => useLiveKitBroadcast('channel', 'viewer', []))
    await waitFor(() => expect(result.current.status?.active).toBe(true))
    await act(async () => { await result.current.watch() })
    expect(result.current.isPublishing).toBe(false)
    await act(async () => {
      getSharedChannelSocket().onBroadcastTokenGrant?.({
        channel_id: 'channel', token: 'publisher', livekit_url: 'ws://livekit', can_publish: true,
      })
    })
    await waitFor(() => expect(result.current.isPublishing).toBe(true))
    expect(media.rooms).toHaveLength(2)
    expect((media.rooms[1] as FakeRoom).localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(true)
  })

  it('uses a promotion grant received before the member starts watching', async () => {
    const { result } = renderHook(() => useLiveKitBroadcast('channel', 'viewer', []))
    await waitFor(() => expect(result.current.status?.active).toBe(true))
    act(() => {
      getSharedChannelSocket().onBroadcastTokenGrant?.({
        channel_id: 'channel', token: 'publisher', livekit_url: 'ws://livekit', can_publish: true,
      })
    })
    await act(async () => { await result.current.watch() })
    expect(result.current.isPublishing).toBe(true)
    expect(vi.mocked(getBroadcastToken)).not.toHaveBeenCalled()
  })

  it('recovers an unexpected drop with a fresh token and keeps the publisher muted', async () => {
    vi.mocked(getBroadcastToken).mockResolvedValue({
      token: 'publisher', livekit_url: 'ws://livekit', room: 'channel-test',
      max_duration_seconds: 600, can_publish: true,
    })
    vi.mocked(refreshBroadcastToken).mockResolvedValue({
      token: 'fresh', livekit_url: 'ws://livekit', room: 'channel-test',
      max_duration_seconds: 600, can_publish: true,
    })
    const { result } = renderHook(() => useLiveKitBroadcast('channel', 'viewer', []))
    await waitFor(() => expect(result.current.status?.active).toBe(true))
    await act(async () => { await result.current.watch() })
    await act(async () => { await result.current.toggleMute() })
    expect(result.current.isMuted).toBe(true)
    const first = media.rooms[0] as FakeRoom
    const onDisconnected = first.on.mock.calls.find(([event]) => event === 'disconnected')?.[1]
    await act(async () => { onDisconnected?.(3) })
    await waitFor(() => expect(media.rooms).toHaveLength(2))
    expect(vi.mocked(refreshBroadcastToken)).toHaveBeenCalledWith('channel')
    await waitFor(() => expect(result.current.connectionState).toBe('connected'))
    expect((media.rooms[1] as FakeRoom).localParticipant.setMicrophoneEnabled).toHaveBeenCalledWith(false)
    expect(result.current.isMuted).toBe(true)
  })

  it('does not re-mint a token after a deliberate disconnect', async () => {
    const { result } = renderHook(() => useLiveKitBroadcast('channel', 'viewer', []))
    await waitFor(() => expect(result.current.status?.active).toBe(true))
    await act(async () => { await result.current.watch() })
    const onDisconnected = (media.rooms[0] as FakeRoom).on.mock.calls.find(([event]) => event === 'disconnected')?.[1]
    await act(async () => { onDisconnected?.(4) })
    expect(result.current.connectionState).toBe('idle')
    expect(vi.mocked(refreshBroadcastToken)).not.toHaveBeenCalled()
    expect(media.rooms).toHaveLength(1)
  })
})
