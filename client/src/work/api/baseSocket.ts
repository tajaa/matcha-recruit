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

function getWsBase(): string {
  const base = import.meta.env.VITE_API_URL ?? '/api'
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
   * because no auth token was in localStorage yet.
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
    const token = localStorage.getItem('matcha_access_token')
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
  }

  /** Send a frame if the socket is open; a no-op otherwise. */
  protected send(data: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
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
    // server isn't hammered every 3s indefinitely. Reset to 0 on a clean open.
    const delay = Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * 2 ** this._reconnectAttempts)
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
    const before = localStorage.getItem('matcha_access_token')
    const { ensureFreshToken } = await import('../../api/client')
    const after = await ensureFreshToken()
    if (this._closed) return
    if (after && after !== before) {
      this._reconnectAttempts = 0
      this._scheduleReconnect()
    }
  }
}
