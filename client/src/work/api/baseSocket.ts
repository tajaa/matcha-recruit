/**
 * Shared WebSocket transport for the three matcha-work sockets (threads,
 * projects, channels).
 *
 * Those three carried byte-identical copies of everything below — the ws base
 * URL, the token-as-subprotocol handshake, the 30s ping, the capped backoff,
 * the 4001/4003 auth-failure refresh dance, and the disconnect teardown. Only
 * three things actually differ per socket, and those are the abstract members:
 * the URL path, the message dispatch, and what to re-send on reconnect.
 *
 * Triplicating this wasn't just volume — it let the copies drift. channelSocket
 * answered the server's `server_ping` with a `pong` and the other two did not,
 * so a server-side liveness probe on a thread or project connection went
 * unanswered. That handling now lives here and applies to all three.
 */

import { API_BASE } from '../../api/client'
import { getAccessToken } from '../../api/authStorage'

function getWsBase(): string {
  const base = API_BASE
  if (base.startsWith('http')) {
    return base.replace(/^http/, 'ws').replace(/\/api$/, '')
  }
  // Relative URL — build from window.location
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}`
}

const WS_BASE = getWsBase()

/** Backend close codes for "this token is not acceptable". */
const AUTH_CLOSE_CODES = new Set([4001, 4003])

const PING_INTERVAL_MS = 30_000
const BACKOFF_BASE_MS = 3_000
const BACKOFF_MAX_MS = 30_000

export abstract class BaseSocket {
  private ws: WebSocket | null = null
  private pingInterval: ReturnType<typeof setInterval> | null = null
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  private _closed = false
  private _reconnectAttempts = 0
  private _onVisibilityChange = () => {
    if (document.visibilityState === 'visible') this._wake()
  }
  private _onOnline = () => this._wake()

  constructor() {
    // Laptop sleep / network change recovery. The OS can freeze or kill the
    // socket without a prompt onclose, and background tabs throttle the
    // backoff timer to ~1/min — so on wake, reconnect immediately and (even
    // if the socket looks open) fire connected-listeners so the channel
    // view's reconnect catch-up refetch runs. Espresso does the same via
    // didBecomeActiveNotification for exactly this reason.
    //
    // NOTE: this is only a true process-lifetime singleton for
    // getSharedChannelSocket(). ProjectSocket/ThreadSocket are constructed
    // per-mount (useKanbanBoard, useProjectPresence, useThreadCollaboration),
    // and disconnectSharedChannelSocket() itself replaces the channel
    // singleton on every logout/login — so these listeners ARE removed in
    // disconnect() below rather than assumed to outlive the instance.
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', this._onVisibilityChange)
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('online', this._onOnline)
    }
  }

  private _wake() {
    if (this._closed) return
    if (this.isOpen) {
      // Possibly a zombie socket (frozen tab) — the catch-up refetch is the
      // recovery either way; the next ping cycle flushes a true zombie out.
      this._emit(this.connectedListeners)
      return
    }
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }
    this._reconnectAttempts = 0
    this.connect()
  }

  // Listener SETS, not single slots. The channel socket is a process-wide
  // singleton shared by useChannelSocket, useChannelNotifications and
  // useLiveKitCall; with one slot each, the last hook to mount silently
  // clobbered the others' handler and nulled it on unmount. channelSocket had
  // already learned this for messages (addMessageListener) — this is the same
  // fix for the lifecycle callbacks.
  private connectedListeners = new Set<() => void>()
  private disconnectedListeners = new Set<() => void>()

  /** Returns an unsubscribe function, so a hook's cleanup is one call. */
  addConnectedListener(fn: () => void): () => void {
    this.connectedListeners.add(fn)
    return () => this.connectedListeners.delete(fn)
  }

  addDisconnectedListener(fn: () => void): () => void {
    this.disconnectedListeners.add(fn)
    return () => this.disconnectedListeners.delete(fn)
  }

  private _emit(listeners: Set<() => void>) {
    // One throwing listener must not stop the others, and must not escape into
    // the WebSocket event handler.
    for (const fn of listeners) {
      try { fn() } catch { /* isolated */ }
    }
  }

  get isOpen(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  /**
   * Whether connect() has ever produced a socket object. Distinct from isOpen:
   * getSharedChannelSocket uses this to retry a connect() that bailed early
   * because no auth token was in the tab session yet.
   */
  get hasSocket(): boolean {
    return this.ws !== null
  }

  /** WS path for this socket, e.g. `/ws/threads`. */
  protected abstract path(): string

  /**
   * Handle one parsed server frame. Return value is ignored; throwing is
   * contained by the caller. `ping`/`server_ping` are handled before this runs.
   */
  protected abstract handleMessage(data: Record<string, unknown>): void

  /**
   * Re-send whatever room/thread/project membership this socket had before the
   * connection dropped. Called on every successful open, including the first —
   * implementations must no-op when there is nothing joined yet.
   */
  protected abstract rejoin(): void

  /** Optional: send a graceful leave frame before an explicit disconnect(). */
  protected beforeDisconnect(): void {}

  /** Optional: drop local membership state on an explicit disconnect(). */
  protected clearState(): void {}

  connect() {
    this._closed = false
    // Genuinely idempotent, which getSharedChannelSocket's comment has always
    // claimed and this has never done: without the guard a second connect()
    // overwrote this.ws and orphaned a still-open socket that kept receiving
    // frames nobody read. CONNECTING counts as in-flight — the open handler
    // will fire.
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return
    }
    // A manual connect() supersedes a scheduled retry; leaving it armed builds
    // a second socket a few seconds later.
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }
    // Raw read, not ensureFreshToken(): connect() must stay sync — the
    // WebSocket constructor call below can't await a refresh.
    const token = getAccessToken()
    if (!token) return

    try {
      // Token rides the Sec-WebSocket-Protocol header, not the URL — query
      // strings land in nginx/proxy access logs. Server echoes 'bearer'.
      this.ws = new WebSocket(`${WS_BASE}${this.path()}`, ['bearer', token])
    } catch {
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this._reconnectAttempts = 0
      this._emit(this.connectedListeners)
      this._startPing()
      this.rejoin()
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        // Server-initiated liveness probe. Answering it is what keeps the
        // connection from being reaped as idle; previously only channelSocket
        // did, so thread/project connections looked dead to the server.
        if (data.type === 'server_ping') {
          this.send({ type: 'pong' })
          return
        }
        this.handleMessage(data)
      } catch { /* malformed frame — ignore */ }
    }

    this.ws.onclose = (event) => {
      this._stopPing()
      this._emit(this.disconnectedListeners)
      if (this._closed) return
      // Don't reconnect with a token the server just rejected — try one refresh
      // and reconnect only if it produced a genuinely new one.
      if (AUTH_CLOSE_CODES.has(event.code)) {
        void this._reconnectAfterAuthFailure()
      } else {
        this._scheduleReconnect()
      }
    }

    this.ws.onerror = () => {
      this.ws?.close()
    }
  }

  disconnect() {
    this._closed = true
    this._stopPing()
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }
    // Ordered: the leave frame must go out while the socket is still OPEN.
    this.beforeDisconnect()
    this.ws?.close()
    this.ws = null
    this.clearState()
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', this._onVisibilityChange)
    }
    if (typeof window !== 'undefined') {
      window.removeEventListener('online', this._onOnline)
    }
  }

  /** Send a frame if the socket is open. Returns false when the frame was
   * dropped (closed / reconnecting) so callers can queue it for replay —
   * the old void signature silently ate messages sent during a backoff
   * window, the primary cross-device divergence cause. */
  protected send(data: Record<string, unknown>): boolean {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
      return true
    }
    return false
  }

  private _startPing() {
    this._stopPing()
    this.pingInterval = setInterval(() => {
      this.send({ type: 'ping' })
    }, PING_INTERVAL_MS)
  }

  private _stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval)
      this.pingInterval = null
    }
  }

  private _scheduleReconnect() {
    if (this._closed) return
    // Capped exponential backoff (3s, 6s, 12s, 24s, … max 30s) so a downed
    // server isn't hammered every 3s indefinitely. Reset to 0 on a clean
    // open. +0-1s jitter: a server blip disconnects every client
    // simultaneously; deterministic backoff reconnects them all at exactly
    // t+3s and every one fires its catch-up history fetch in the same
    // instant.
    const delay =
      Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * 2 ** this._reconnectAttempts) +
      Math.random() * 1000
    this._reconnectAttempts++
    this.reconnectTimeout = setTimeout(() => {
      this.connect()
    }, delay)
  }

  // After an auth-class close (4001/4003): refresh the token once and reconnect
  // only if a genuinely new token was obtained. If the token is unchanged the
  // server would just reject it again; if refresh failed, ensureFreshToken has
  // already triggered logout — either way, stop the loop.
  private async _reconnectAfterAuthFailure() {
    if (this._closed) return
    // Raw read for a before/after diff around the ensureFreshToken() call
    // below — the point of this read is to compare, not to attach a header.
    const before = getAccessToken()
    const { ensureFreshToken } = await import('../../api/client')
    const after = await ensureFreshToken()
    if (this._closed) return
    if (after && after !== before) {
      this._reconnectAttempts = 0
      this._scheduleReconnect()
    }
  }
}
