import type { MWMessage } from '../types/matcha-work'

type NewMessageHandler = (messages: MWMessage[]) => void
type TypingHandler = (user: { id: string; name: string }) => void
type OnlineHandler = (users: { id: string; name: string }[]) => void
type UserEventHandler = (user: { id: string; name: string }) => void

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

export class ThreadSocket {
  private ws: WebSocket | null = null
  private pingInterval: ReturnType<typeof setInterval> | null = null
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  private currentThread: string | null = null
  private _closed = false

  onNewMessage: NewMessageHandler | null = null
  onTyping: TypingHandler | null = null
  onOnlineUsers: OnlineHandler | null = null
  onUserJoined: UserEventHandler | null = null
  onUserLeft: UserEventHandler | null = null
  onConnected: (() => void) | null = null
  onDisconnected: (() => void) | null = null

  connect() {
    this._closed = false
    const token = localStorage.getItem('matcha_access_token')
    if (!token) return

    try {
      this.ws = new WebSocket(`${WS_BASE}/ws/threads?token=${token}`)
    } catch {
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this.onConnected?.()
      this._startPing()
      // Rejoin thread if we were in one
      if (this.currentThread) {
        this._send({ type: 'join_thread', thread_id: this.currentThread })
      }
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        switch (data.type) {
          case 'new_messages':
            this.onNewMessage?.(data.messages)
            break
          case 'typing':
            this.onTyping?.(data.user)
            break
          case 'online_users':
            this.onOnlineUsers?.(data.users)
            break
          case 'user_joined':
            this.onUserJoined?.(data.user)
            break
          case 'user_left':
            this.onUserLeft?.(data.user)
            break
        }
      } catch { /* ignore malformed messages */ }
    }

    this.ws.onclose = () => {
      this._stopPing()
      this.onDisconnected?.()
      if (!this._closed) this._scheduleReconnect()
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
    this.ws?.close()
    this.ws = null
    this.currentThread = null
  }

  joinThread(threadId: string) {
    this.currentThread = threadId
    this._send({ type: 'join_thread', thread_id: threadId })
  }

  leaveThread(threadId: string) {
    this._send({ type: 'leave_thread', thread_id: threadId })
    if (this.currentThread === threadId) this.currentThread = null
  }

  sendTyping(threadId: string) {
    this._send({ type: 'typing', thread_id: threadId })
  }

  private _send(data: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  private _startPing() {
    this._stopPing()
    this.pingInterval = setInterval(() => {
      this._send({ type: 'ping' })
    }, 30000)
  }

  private _stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval)
      this.pingInterval = null
    }
  }

  private _scheduleReconnect() {
    if (this._closed) return
    this.reconnectTimeout = setTimeout(() => {
      this.connect()
    }, 3000)
  }
}
