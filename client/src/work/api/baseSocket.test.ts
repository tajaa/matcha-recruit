import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { BaseSocket } from './baseSocket'
import { clearAuthTokens, setAuthTokens } from '../../api/authStorage'

// A minimal WebSocket stand-in. jsdom has no WebSocket, and the behaviour under
// test is entirely about how BaseSocket reacts to open/message/close — so a fake
// we can drive frame-by-frame is more useful here than a real connection.
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

  url: string
  protocols?: string[]

  constructor(url: string, protocols?: string[]) {
    this.url = url
    this.protocols = protocols
    FakeWebSocket.instances.push(this)
  }
  send(data: string) { this.sent.push(data) }
  close() { this.readyState = FakeWebSocket.CLOSED }

  // -- test drivers --
  open() { this.onopen?.() }
  receive(obj: unknown) { this.onmessage?.({ data: JSON.stringify(obj) }) }
  serverClose(code = 1006) { this.readyState = FakeWebSocket.CLOSED; this.onclose?.({ code }) }
  frames() { return this.sent.map((s) => JSON.parse(s)) }
}

class TestSocket extends BaseSocket {
  joined: string | null = null
  handled: Record<string, unknown>[] = []
  leaveSent = false
  cleared = false

  protected path() { return '/ws/test' }
  protected rejoin() {
    if (this.joined) this.send({ type: 'join', id: this.joined })
  }
  protected handleMessage(data: Record<string, unknown>) { this.handled.push(data) }
  protected beforeDisconnect() { this.leaveSent = this.isOpen; this.send({ type: 'leave' }) }
  protected clearState() { this.cleared = true }

  // Exposes the protected send() so tests can assert on its return value.
  trySend(data: Record<string, unknown>): boolean {
    return this.send(data)
  }
}

const latest = () => FakeWebSocket.instances[FakeWebSocket.instances.length - 1]

describe('BaseSocket', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
    setAuthTokens('tok-1', 'refresh-1')
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    clearAuthTokens()
  })

  it('sends the token as a subprotocol, never in the URL', () => {
    const s = new TestSocket()
    s.connect()
    // A token in the query string lands in nginx access logs — the whole reason
    // these sockets use Sec-WebSocket-Protocol.
    expect(latest().url).not.toContain('tok-1')
    expect(latest().protocols).toEqual(['bearer', 'tok-1'])
  })

  it('does not connect without a token', () => {
    clearAuthTokens()
    new TestSocket().connect()
    expect(FakeWebSocket.instances).toHaveLength(0)
  })

  it('answers a server_ping with a pong without reaching handleMessage', () => {
    // The drift this extraction fixed: only channelSocket used to reply, so the
    // server saw thread/project connections as unresponsive.
    const s = new TestSocket()
    s.connect()
    latest().open()
    latest().receive({ type: 'server_ping' })
    expect(latest().frames()).toContainEqual({ type: 'pong' })
    expect(s.handled).toHaveLength(0)
  })

  it('routes non-ping frames to handleMessage', () => {
    const s = new TestSocket()
    s.connect()
    latest().open()
    latest().receive({ type: 'message', body: 'hi' })
    expect(s.handled).toEqual([{ type: 'message', body: 'hi' }])
  })

  it('ignores malformed frames instead of throwing', () => {
    const s = new TestSocket()
    s.connect()
    latest().open()
    expect(() => latest().onmessage?.({ data: 'not json{' })).not.toThrow()
    expect(s.handled).toHaveLength(0)
  })

  it('rejoins on every open, including after a reconnect', () => {
    const s = new TestSocket()
    s.joined = 'room-1'
    s.connect()
    latest().open()
    expect(latest().frames()).toContainEqual({ type: 'join', id: 'room-1' })

    latest().serverClose(1006)
    vi.advanceTimersByTime(4000) // base 3000 + up to 1000 jitter
    latest().open()
    expect(latest().frames()).toContainEqual({ type: 'join', id: 'room-1' })
  })

  it('backs off exponentially and caps at 30s', () => {
    const s = new TestSocket()
    s.connect()
    const delays = [3000, 6000, 12000, 24000, 30000, 30000]
    for (const d of delays) {
      latest().serverClose(1006)
      const before = FakeWebSocket.instances.length
      // Nothing reconnects before the base delay — jitter only adds, never
      // subtracts (+0-1000ms, see baseSocket.ts's _scheduleReconnect).
      vi.advanceTimersByTime(d - 1)
      expect(FakeWebSocket.instances.length).toBe(before)
      // Covers the full jitter range on top of the base delay.
      vi.advanceTimersByTime(1001)
      expect(FakeWebSocket.instances.length).toBe(before + 1)
    }
  })

  it('resets the backoff after a successful open', () => {
    const s = new TestSocket()
    s.connect()
    latest().serverClose(1006)
    vi.advanceTimersByTime(4000) // base 3000 + up to 1000 jitter
    latest().serverClose(1006)
    vi.advanceTimersByTime(7000) // base 6000 + up to 1000 jitter
    latest().open() // clean connection — attempts reset

    latest().serverClose(1006)
    const before = FakeWebSocket.instances.length
    vi.advanceTimersByTime(4000) // reset -> base delay 3000 again + jitter
    expect(FakeWebSocket.instances.length).toBe(before + 1)
  })

  it('does NOT auto-reconnect on an auth-class close', () => {
    // 4001/4003 mean the token was rejected; reconnecting with the same token
    // would spin forever. The refresh path is async and deliberately separate.
    const s = new TestSocket()
    s.connect()
    latest().serverClose(4001)
    const before = FakeWebSocket.instances.length
    vi.advanceTimersByTime(60_000)
    expect(FakeWebSocket.instances.length).toBe(before)
  })

  it('stops reconnecting after an explicit disconnect', () => {
    const s = new TestSocket()
    s.connect()
    latest().open()
    s.disconnect()
    const before = FakeWebSocket.instances.length
    vi.advanceTimersByTime(60_000)
    expect(FakeWebSocket.instances.length).toBe(before)
  })

  it('sends the leave frame while still open, then clears state', () => {
    // Ordering matters: beforeDisconnect must run before ws.close(), or the
    // graceful leave is silently dropped by the readyState guard in send().
    const s = new TestSocket()
    s.connect()
    latest().open()
    s.disconnect()
    expect(s.leaveSent).toBe(true)
    expect(latest().frames()).toContainEqual({ type: 'leave' })
    expect(s.cleared).toBe(true)
  })

  it('pings every 30s while open and stops after close', () => {
    const s = new TestSocket()
    s.connect()
    latest().open()
    const ws = latest()
    vi.advanceTimersByTime(90_000)
    expect(ws.frames().filter((f) => f.type === 'ping')).toHaveLength(3)

    const count = ws.sent.length
    ws.serverClose(1006)
    vi.advanceTimersByTime(90_000)
    expect(ws.sent.length).toBe(count)
  })

  it('is idempotent: a second connect() does not orphan the open socket', () => {
    // getSharedChannelSocket's comment always claimed this; the code never did,
    // so a stray connect() left a live socket nobody read frames from.
    const s = new TestSocket()
    s.connect()
    latest().open()
    s.connect()
    s.connect()
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('a manual connect() cancels a scheduled reconnect instead of racing it', () => {
    const s = new TestSocket()
    s.connect()
    latest().serverClose(1006) // arms a 3s retry
    s.connect()                // supersedes it
    expect(FakeWebSocket.instances).toHaveLength(2)
    vi.advanceTimersByTime(10_000)
    expect(FakeWebSocket.instances).toHaveLength(2) // the armed retry did not also fire
  })

  it('fans connect/disconnect out to every listener, and unsubscribes only its own', () => {
    // The shared channel socket has three consumers; single-slot handlers meant
    // the last one to mount silently replaced the others.
    const s = new TestSocket()
    const a: string[] = []
    const offA = s.addConnectedListener(() => a.push('a'))
    s.addConnectedListener(() => a.push('b'))
    s.connect()
    latest().open()
    expect(a).toEqual(['a', 'b'])

    offA()
    latest().serverClose(1006)
    vi.advanceTimersByTime(3000)
    latest().open()
    expect(a).toEqual(['a', 'b', 'b'])
  })

  it('a throwing listener does not stop the others', () => {
    const s = new TestSocket()
    const seen: string[] = []
    s.addConnectedListener(() => { throw new Error('boom') })
    s.addConnectedListener(() => seen.push('ran'))
    s.connect()
    expect(() => latest().open()).not.toThrow()
    expect(seen).toEqual(['ran'])
  })

  it('drops sends when the socket is not open', () => {
    const s = new TestSocket()
    s.connect()
    const ws = latest()
    ws.readyState = FakeWebSocket.CLOSED
    s.joined = 'room-1'
    ws.open()
    expect(ws.sent).toHaveLength(0)
  })

  it('send() reports success/failure via its return value', () => {
    // Callers (channelSocket's outbox) need this to know whether to queue a
    // frame for replay — the old void signature silently ate it either way.
    const s = new TestSocket()
    expect(s.trySend({ type: 'ping' })).toBe(false) // no socket yet
    s.connect()
    latest().open()
    expect(s.trySend({ type: 'ping' })).toBe(true)
    latest().readyState = FakeWebSocket.CLOSED
    expect(s.trySend({ type: 'ping' })).toBe(false)
  })

  it('wakes on visibilitychange: reconnects if closed, re-fires connected listeners if open', () => {
    const s = new TestSocket()
    const seen: string[] = []
    s.addConnectedListener(() => seen.push('connected'))
    s.connect()
    latest().open()
    expect(seen).toEqual(['connected'])

    // Tab already open at wake time (OS froze it without a close event) —
    // fire connected-listeners again so the reconnect catch-up refetch runs.
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
    expect(seen).toEqual(['connected', 'connected'])

    // Socket actually dead — wake reconnects immediately, bypassing backoff.
    latest().serverClose(1006)
    const before = FakeWebSocket.instances.length
    document.dispatchEvent(new Event('visibilitychange'))
    expect(FakeWebSocket.instances.length).toBe(before + 1)
  })

  it('removes its visibilitychange/online listeners on disconnect()', () => {
    // ProjectSocket/ThreadSocket are constructed per-mount (not process-
    // lifetime singletons like the shared channel socket) — without this,
    // every mount left two dead global listeners retaining a closed socket.
    const addSpy = vi.spyOn(document, 'addEventListener')
    const removeSpy = vi.spyOn(document, 'removeEventListener')
    const s = new TestSocket()
    s.connect()
    latest().open()
    const [, visibilityHandler] = addSpy.mock.calls.find(([type]) => type === 'visibilitychange')!
    s.disconnect()
    expect(removeSpy).toHaveBeenCalledWith('visibilitychange', visibilityHandler)
    addSpy.mockRestore()
    removeSpy.mockRestore()
  })

  it('reconnect backoff includes jitter, staying within [base, base+1000)', () => {
    const s = new TestSocket()
    s.connect()
    latest().serverClose(1006) // schedules first retry at ~3000-4000ms
    vi.advanceTimersByTime(2999)
    expect(FakeWebSocket.instances).toHaveLength(1)
    vi.advanceTimersByTime(1001) // covers up to 4000ms elapsed
    expect(FakeWebSocket.instances).toHaveLength(2)
  })
})
