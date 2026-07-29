import { api } from '../client'
import type { UpcomingItem } from '../../types/dashboard'

// ── Task Board ──
//
// Moved here from work/api/matchaWork/tasks.ts (2026-07-28) — the data
// (credential/incident/training/compliance deadlines + manual tasks) is
// core HR-ops content, not a matcha-work concern, and the old
// /matcha-work/tasks* endpoints were gated behind the matcha_work add-on
// most tenants don't have. See server/app/matcha/routes/dashboard/tasks.py.

/** `/dashboard/tasks`'s auto_items carry `source_id` (used for dismissal),
 * but the shared `UpcomingItem` model (mirrors the Pydantic response model
 * on `/dashboard/upcoming`, which doesn't serialize it) doesn't declare the
 * field. */
export interface TaskBoardAutoItem extends UpcomingItem {
  source_id: string
}

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
  auto_items: TaskBoardAutoItem[]
  manual_items: ManualTask[]
  dismissed_ids: string[]
  total: number
}

export function fetchTaskBoard() {
  return api.get<TaskBoardResponse>('/dashboard/tasks')
}

export function createTask(body: { title: string; description?: string; due_date?: string; horizon?: string; priority?: string; link?: string }) {
  return api.post<ManualTask>('/dashboard/tasks', body)
}

export function updateTask(id: string, body: Record<string, unknown>) {
  return api.patch<ManualTask>(`/dashboard/tasks/${id}`, body)
}

export function deleteTask(id: string) {
  return api.delete(`/dashboard/tasks/${id}`)
}

export function dismissAutoTask(source_category: string, source_id: string) {
  return api.post('/dashboard/tasks/dismiss', { source_category, source_id })
}
