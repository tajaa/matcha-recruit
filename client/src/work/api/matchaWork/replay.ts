import { api } from '../../../api/client'

export interface ReplayTask {
  task_id: string | null
  title: string
  column: string
  assignee_name: string | null
  assignee_avatar_url: string | null
}

export interface ReplayEvent {
  id: string
  task_id: string | null
  event_type: string
  from_column: string | null
  to_column: string | null
  actor_id: string | null
  actor_name: string | null
  actor_avatar_url: string | null
  title: string
  created_at: string
}

export interface WeeklyReplay {
  week_start: string
  week_end: string
  starting_state: ReplayTask[]
  events: ReplayEvent[]
}

export function getWeeklyReplay(projectId: string, weekStart: string) {
  return api.get<WeeklyReplay>(
    `/matcha-work/projects/${projectId}/history/replay?week_start=${encodeURIComponent(weekStart)}`,
  )
}
