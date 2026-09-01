import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ChannelSocket, clearChannelOutbox } from './channelSocket'
import { clearAuthTokens, getAccessToken, setAuthTokens } from '../../api/authStorage'

// Same fake-WebSocket approach as baseSocket.test.ts — outbox behavior is
// entirely about what gets replayed on open/error, driven frame-by-frame.
class FakeWebSocket {
  static OPEN = 1
  static CLOSED = 3
  static instances: FakeWebSocket[] = []

  readyState = FakeWebSocket.OPEN
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  onerror: (() => void) | null = null

  constructor(_url: string, _protocols?: string[]) {
    FakeWebSocket.instances.push(this)
  }
  send(data: string) { this.sent.push(data) }
  close() { this.readyState = FakeWebSocket.CLOSED }

  open() { this.onopen?.() }
  receive(obj: unknown) { this.onmessage?.({ data: JSON.stringify(obj) }) }
  frames() { return this.sent.map((s) => JSON.parse(s)) }
}

const latest = () => FakeWebSocket.instances[FakeWebSocket.instances.length - 1]

// A JWT-shaped token whose payload decodes to { sub: <uid> } — the outbox
// key is derived from this, not from a real signature (never verified
// client-side, it's a storage namespace only).
function fakeToken(sub: string): string {
  const header = btoa(JSON.stringify({ alg: 'none' }))
  const payload = btoa(JSON.stringify({ sub }))
  return `${header}.${payload}.sig`
}

describe('ChannelSocket outbox', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
    localStorage.clear()
    sessionStorage.clear()
    setAuthTokens(fakeToken('user-1'), 'refresh-1')
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    clearAuthTokens()
    sessionStorage.clear()
  })

  it('queues a send made while offline, and replays it on reconnect', () => {
    const s = new ChannelSocket()
    s.connect() // no socket open yet (fresh, unconnected FakeWebSocket starts OPEN in this harness)
    // Force the "offline" case explicitly: send() only returns false when
    // readyState !== OPEN.
    latest().readyState = FakeWebSocket.CLOSED
    const sent = s.sendMessage('ch-1', 'hello', undefined, 'cmid-1')
    expect(sent).toBe(false)

    // Reconnect: rejoin() flushes the outbox.
    latest().readyState = FakeWebSocket.OPEN
    latest().open()
    const frames = latest().frames()
    expect(frames.some((f) => f.type === 'message' && f.client_message_id === 'cmid-1')).toBe(true)
  })

  it('keeps a queued entry when the server replies rate_limited, and re-drains it shortly after', () => {
    // The bug this closes: the old handler deleted the outbox entry on ANY
    // error frame, so a burst past the server's token-bucket burst size was
    // silently and permanently lost on replay — exactly the scenario the
    // outbox exists to protect against.
    const s = new ChannelSocket()
    s.connect()
    latest().readyState = FakeWebSocket.CLOSED
    s.sendMessage('ch-1', 'hello', undefined, 'cmid-rl')
    latest().readyState = FakeWebSocket.OPEN
    latest().open() // flush attempt #1 sends it

    latest().receive({ type: 'error', code: 'rate_limited', client_message_id: 'cmid-rl', channel_id: 'ch-1' })

    // Not removed — still queued for a later retry.
    latest().sent = []
    vi.advanceTimersByTime(1300) // past the 1.2s scheduled re-flush
    const replay = latest().frames()
    expect(replay.some((f) => f.type === 'message' && f.client_message_id === 'cmid-rl')).toBe(true)
  })

  it('drops a queued entry on a permanent rejection (not rate_limited)', () => {
    const s = new ChannelSocket()
    s.connect()
    latest().readyState = FakeWebSocket.CLOSED
    s.sendMessage('ch-1', 'hello', undefined, 'cmid-perm')
    latest().readyState = FakeWebSocket.OPEN
    latest().open()

    latest().receive({ type: 'error', code: 'not_a_member', client_message_id: 'cmid-perm', channel_id: 'ch-1' })

    latest().sent = []
    vi.advanceTimersByTime(5000)
    const replay = latest().frames()
    expect(replay.some((f) => f.client_message_id === 'cmid-perm')).toBe(false)
  })

  it('removes an entry once the server echoes the message back', () => {
    const s = new ChannelSocket()
    s.connect()
    latest().readyState = FakeWebSocket.CLOSED
    s.sendMessage('ch-1', 'hello', undefined, 'cmid-echo')
    latest().readyState = FakeWebSocket.OPEN
    latest().open()

    latest().receive({
      type: 'message',
      message: { id: 'srv-1', channel_id: 'ch-1', client_message_id: 'cmid-echo', content: 'hello' },
    })

    latest().sent = []
    vi.advanceTimersByTime(5000)
    expect(latest().frames().some((f) => f.client_message_id === 'cmid-echo')).toBe(false)
  })

  it('dispatches notification frames to listeners and supports cleanup', () => {
    const s = new ChannelSocket()
    const received: string[] = []
    const handler = (notification: { id: string }) => received.push(notification.id)
    s.addNotificationListener(handler)
    s.connect()

    latest().receive({
      type: 'notification',
      notification: {
        id: 'notification-1',
        type: 'huume_offer',
        title: 'Offer accepted',
        body: 'The candidate signed the offer.',
        link: '/work/thread-1',
        metadata: {},
        is_read: false,
        created_at: '2026-08-14T00:00:00Z',
      },
    })
    expect(received).toEqual(['notification-1'])

    s.removeNotificationListener(handler)
    latest().receive({
      type: 'notification',
      notification: { id: 'notification-2' },
    })
    expect(received).toEqual(['notification-1'])
  })

  it('scopes the outbox to the current user, so a different login does not replay it', () => {
    const s1 = new ChannelSocket()
    s1.connect()
    latest().readyState = FakeWebSocket.CLOSED
    s1.sendMessage('ch-1', 'from user 1', undefined, 'cmid-u1')

    // Simulate logout -> different user logging in on the same browser.
    setAuthTokens(fakeToken('user-2'), 'refresh-2')
    const s2 = new ChannelSocket()
    s2.connect()
    latest().readyState = FakeWebSocket.OPEN
    latest().open()

    // user-2's flush must not carry user-1's queued send.
    expect(latest().frames().some((f) => f.client_message_id === 'cmid-u1')).toBe(false)
  })

  it('clearChannelOutbox drops the outbox for the token it is given, independent of the current token', () => {
    const s = new ChannelSocket()
    s.connect()
    latest().readyState = FakeWebSocket.CLOSED
    const outgoingToken = getAccessToken()
    s.sendMessage('ch-1', 'hello', undefined, 'cmid-logout')

    // Token already rotated by the time the async logout cleanup runs, as
    // it does for real in api/client.ts's _logout().
    setAuthTokens(fakeToken('user-3'), 'refresh-3')
    clearChannelOutbox(outgoingToken)

    const s2 = new ChannelSocket()
    // Re-set back to user-1's token to prove the entry is actually gone,
    // not just unreachable under user-3's key.
    setAuthTokens(outgoingToken!, 'refresh-2')
    s2.connect()
    latest().readyState = FakeWebSocket.OPEN
    latest().open()
    expect(latest().frames().some((f) => f.client_message_id === 'cmid-logout')).toBe(false)
  })
})
