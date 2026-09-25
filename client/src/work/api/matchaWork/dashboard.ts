import { api } from '../../../api/client'

export interface MWOpenTask {
  id: string
  project_id: string
  title: string
  priority: string
  status: string
  due_date: string | null
  progress_note: string | null
  assigned_to: string
  created_by: string
  updated_at: string
  project_title: string | null
  project_type: string | null
  is_subtask: boolean
  parent_task_id?: string
  parent_title?: string
}

export interface MWActivityItem {
  kind: 'project' | 'task' | 'thread' | 'journal'
  ref_id: string
  project_id: string | null
  title: string
  project_type: string | null
  updated_at: string
}

export const listOpenTasks = () => api.get<MWOpenTask[]>('/matcha-work/tasks/open')
export const listRecentActivity = () => api.get<MWActivityItem[]>('/matcha-work/activity/recent')
