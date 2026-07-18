import { api } from '../../../api/client'
import type { UpcomingItem } from '../../../types/dashboard'

// ── Task Board ──

export interface ManualTask {
  id: string
  title: string
  description: string | null
  due_date: string | null
  date: string | null
  days_until: number | null
  horizon: string | null
  priority: string
  status: string
  completed_at: string | null
  link: string | null
  category: string
  source: 'manual'
  created_at: string
  updated_at: string
}

export interface TaskBoardResponse {
  auto_items: UpcomingItem[]
  manual_items: ManualTask[]
  dismissed_ids: string[]
  total: number
}

export function fetchTaskBoard() {
  return api.get<TaskBoardResponse>('/matcha-work/tasks')
}

export function createTask(body: { title: string; description?: string; due_date?: string; horizon?: string; priority?: string; link?: string }) {
  return api.post<ManualTask>('/matcha-work/tasks', body)
}

export function updateTask(id: string, body: Record<string, unknown>) {
  return api.patch<ManualTask>(`/matcha-work/tasks/${id}`, body)
}

export function deleteTask(id: string) {
  return api.delete(`/matcha-work/tasks/${id}`)
}

export function dismissAutoTask(source_category: string, source_id: string) {
  return api.post('/matcha-work/tasks/dismiss', { source_category, source_id })
}
