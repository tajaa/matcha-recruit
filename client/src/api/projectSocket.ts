/**
 * Project WebSocket — real-time presence (cursor + caret + cross-tab) for
 * matcha-work projects. Mirrors the threadSocket.ts pattern: JWT in query
 * string, auto-reconnect on close, ping every 30s, typed callbacks per event.
 *
 * Routing model:
 * - join_project carries a project_id + page_key. Server tracks user as "in
 *   project_id" (drives the CollaboratorsPill across all sub-tabs) AND "on
 *   page_key" (cursors fan out only between users on the same sub-tab).
 * - page_change moves the user between sub-tabs without leaving the project.
 * - cursor_move / caret_move are throttled client-side (50ms / 100ms in the
 *   useProjectPresence hook). Server enforces an absolute 25/sec cap.
 */

export interface PresenceMember {
  id: string
  name: string
  email: string
  role: string
  avatar_url: string | null
  page_key: string | null
}

export interface CursorPayload {
  user_id: string
  x_pct: number
  y_pct: number
}

export interface CaretPayload {
  user_id: string
  section_id: string
  anchor: number
  head: number
}

type PresenceHandler = (members: PresenceMember[]) => void
type PresenceUpdateHandler = (user_id: string, page_key: string | null) => void
type CursorHandler = (payload: CursorPayload) => void
type CaretHandler = (payload: CaretPayload) => void
type UserEventHandler = (member: Partial<PresenceMember> & { id: string }) => void

function getWsBase(): string {
  const base = import.meta.env.VITE_API_URL ?? '/api'
  if (base.startsWith('http')) {
    return base.replace(/^http/, 'ws').replace(/\/api$/, '')
  }
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}`
}

const WS_BASE = getWsBase()

export class ProjectSocket {
  private ws: WebSocket | null = null
  private pingInterval: ReturnType<typeof setInterval> | null = null
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  private currentProject: string | null = null
  private currentPageKey: string | null = null
  private _closed = false

  onPresence: PresenceHandler | null = null
  onPresenceUpdate: PresenceUpdateHandler | null = null
  onCursor: CursorHandler | null = null
  onCaret: CaretHandler | null = null
  onUserJoined: UserEventHandler | null = null
  onUserLeft: UserEventHandler | null = null
  onConnected: (() => void) | null = null
  onDisconnected: (() => void) | null = null

  connect() {
    this._closed = false
    const token = localStorage.getItem('matcha_access_token')
    if (!token) return

    try {
      this.ws = new WebSocket(`${WS_BASE}/ws/projects?token=${token}`)
    } catch {
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this.onConnected?.()
      this._startPing()
      // Rejoin the project we were tracking before the reconnect.
      if (this.currentProject && this.currentPageKey) {
        this._send({
          type: 'join_project',
          project_id: this.currentProject,
          page_key: this.currentPageKey,
        })
      }
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        switch (data.type) {
          case 'presence':
            this.onPresence?.(data.members)
            break
          case 'presence_update':
            this.onPresenceUpdate?.(data.user_id, data.page_key ?? null)
            break
          case 'cursor':
            this.onCursor?.({
              user_id: data.user_id,
              x_pct: data.x_pct,
              y_pct: data.y_pct,
            })
            break
          case 'caret':
            this.onCaret?.({
              user_id: data.user_id,
              section_id: data.section_id,
              anchor: data.anchor,
              head: data.head,
            })
            break
          case 'user_joined_project':
            this.onUserJoined?.({ ...data.user, page_key: data.page_key })
            break
          case 'user_left_project':
            this.onUserLeft?.({ id: data.user_id })
            break
        }
      } catch { /* malformed — ignore */ }
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
    if (this.currentProject) {
      this._send({ type: 'leave_project', project_id: this.currentProject })
    }
    this.ws?.close()
    this.ws = null
    this.currentProject = null
    this.currentPageKey = null
  }

  joinProject(projectId: string, pageKey: string) {
    this.currentProject = projectId
    this.currentPageKey = pageKey
    this._send({ type: 'join_project', project_id: projectId, page_key: pageKey })
  }

  setPageKey(pageKey: string) {
    if (!this.currentProject) return
    if (this.currentPageKey === pageKey) return
    this.currentPageKey = pageKey
    this._send({
      type: 'page_change',
      project_id: this.currentProject,
      page_key: pageKey,
    })
  }

  sendCursor(xPct: number, yPct: number) {
    if (!this.currentProject || !this.currentPageKey) return
    this._send({
      type: 'cursor_move',
      project_id: this.currentProject,
      page_key: this.currentPageKey,
      x_pct: xPct,
      y_pct: yPct,
    })
  }

  sendCaret(sectionId: string, anchor: number, head: number) {
    if (!this.currentProject || !this.currentPageKey) return
    this._send({
      type: 'caret_move',
      project_id: this.currentProject,
      page_key: this.currentPageKey,
      section_id: sectionId,
      anchor,
      head,
    })
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
