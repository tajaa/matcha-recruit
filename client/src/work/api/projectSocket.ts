/**
 * Project WebSocket — real-time presence (cursor + caret + cross-tab) for
 * matcha-work projects. Transport (connect/ping/backoff/auth-refresh) lives in
 * BaseSocket; this file is the routing model and dispatch.
 *
 * Routing model:
 * - join_project carries a project_id + page_key. Server tracks user as "in
 *   project_id" (drives the CollaboratorsPill across all sub-tabs) AND "on
 *   page_key" (cursors fan out only between users on the same sub-tab).
 * - page_change moves the user between sub-tabs without leaving the project.
 * - cursor_move / caret_move are throttled client-side (50ms / 100ms in the
 *   useProjectPresence hook). Server enforces an absolute 25/sec cap.
 */
import { BaseSocket } from './baseSocket'

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
// `task` is the raw row dict from `broadcast_task_event` (server/app/matcha/
// routes/project_ws.py) — same shape `listProjectTasks`/`updateProjectTask`
// return, plus `actor_id` for self-echo suppression. Untyped here (consumers
// cast to MWProjectTask) to avoid this socket module depending on matcha-work
// domain types.
type TaskEventHandler = (task: Record<string, unknown>) => void
type TaskDeletedHandler = (taskId: string, actorId: string | null) => void

export class ProjectSocket extends BaseSocket {
  private currentProject: string | null = null
  private currentPageKey: string | null = null

  onPresence: PresenceHandler | null = null
  onPresenceUpdate: PresenceUpdateHandler | null = null
  onCursor: CursorHandler | null = null
  onCaret: CaretHandler | null = null
  onUserJoined: UserEventHandler | null = null
  onUserLeft: UserEventHandler | null = null
  onTaskCreated: TaskEventHandler | null = null
  onTaskUpdated: TaskEventHandler | null = null
  onTaskDeleted: TaskDeletedHandler | null = null

  protected path() {
    return '/ws/projects'
  }

  protected rejoin() {
    // Rejoin the project we were tracking before the reconnect.
    if (this.currentProject && this.currentPageKey) {
      this.send({
        type: 'join_project',
        project_id: this.currentProject,
        page_key: this.currentPageKey,
      })
    }
  }

  protected beforeDisconnect() {
    if (this.currentProject) {
      this.send({ type: 'leave_project', project_id: this.currentProject })
    }
  }

  protected clearState() {
    this.currentProject = null
    this.currentPageKey = null
  }

  protected handleMessage(data: Record<string, unknown>) {
    const task = data.task as Record<string, unknown> | undefined
    switch (data.type) {
      case 'presence':
        this.onPresence?.(data.members as PresenceMember[])
        break
      case 'presence_update':
        this.onPresenceUpdate?.(data.user_id as string, (data.page_key as string) ?? null)
        break
      case 'cursor':
        this.onCursor?.({
          user_id: data.user_id as string,
          x_pct: data.x_pct as number,
          y_pct: data.y_pct as number,
        })
        break
      case 'caret':
        this.onCaret?.({
          user_id: data.user_id as string,
          section_id: data.section_id as string,
          anchor: data.anchor as number,
          head: data.head as number,
        })
        break
      case 'user_joined_project':
        this.onUserJoined?.({
          ...(data.user as Partial<PresenceMember> & { id: string }),
          page_key: (data.page_key as string) ?? null,
        })
        break
      case 'user_left_project':
        this.onUserLeft?.({ id: data.user_id as string })
        break
      case 'task.created':
        this.onTaskCreated?.(task as Record<string, unknown>)
        break
      case 'task.updated':
        this.onTaskUpdated?.(task as Record<string, unknown>)
        break
      case 'task.deleted':
        this.onTaskDeleted?.(task?.id as string, (task?.actor_id as string) ?? null)
        break
    }
  }

  joinProject(projectId: string, pageKey: string) {
    this.currentProject = projectId
    this.currentPageKey = pageKey
    this.send({ type: 'join_project', project_id: projectId, page_key: pageKey })
  }

  setPageKey(pageKey: string) {
    if (!this.currentProject) return
    if (this.currentPageKey === pageKey) return
    this.currentPageKey = pageKey
    this.send({
      type: 'page_change',
      project_id: this.currentProject,
      page_key: pageKey,
    })
  }

  sendCursor(xPct: number, yPct: number) {
    if (!this.currentProject || !this.currentPageKey) return
    this.send({
      type: 'cursor_move',
      project_id: this.currentProject,
      page_key: this.currentPageKey,
      x_pct: xPct,
      y_pct: yPct,
    })
  }

  sendCaret(sectionId: string, anchor: number, head: number) {
    if (!this.currentProject || !this.currentPageKey) return
    this.send({
      type: 'caret_move',
      project_id: this.currentProject,
      page_key: this.currentPageKey,
      section_id: sectionId,
      anchor,
      head,
    })
  }
}
