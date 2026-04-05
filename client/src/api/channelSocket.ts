import type { ChannelMessage } from './channels'

type MessageHandler = (msg: ChannelMessage) => void
type TypingHandler = (user: { id: string; name: string }) => void
type OnlineHandler = (users: { id: string; name: string; avatar_url: string | null }[]) => void
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

export class ChannelSocket {
  private ws: WebSocket | null = null
  private pingInterval: ReturnType<typeof setInterval> | null = null
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  private currentRoom: string | null = null
  private _closed = false

  onMessage: MessageHandler | null = null
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
      this.ws = new WebSocket(`${WS_BASE}/ws/channels?token=${token}`)
    } catch {
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this.onConnected?.()
      this._startPing()
      // Rejoin room if we were in one
      if (this.currentRoom) {
        this._send({ type: 'join_room', channel_id: this.currentRoom })
      }
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        switch (data.type) {
          case 'message':
            this.onMessage?.(data.message)
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
    this.currentRoom = null
  }

  joinRoom(channelId: string) {
    this.currentRoom = channelId
    this._send({ type: 'join_room', channel_id: channelId })
  }

  leaveRoom(channelId: string) {
    this._send({ type: 'leave_room', channel_id: channelId })
    if (this.currentRoom === channelId) this.currentRoom = null
  }

  sendMessage(channelId: string, content: string, attachments?: { url: string; filename: string; content_type: string; size: number }[]) {
    this._send({ type: 'message', channel_id: channelId, content, ...(attachments?.length ? { attachments } : {}) })
  }

  sendTyping(channelId: string) {
    this._send({ type: 'typing', channel_id: channelId })
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
