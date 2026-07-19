import { api } from '../../../api/client'
import type {
  MWProjectTask,
  MWProjectTaskCreate,
  MWProjectTaskPatch,
  MWSubtask,
  MWTaskDraft,
  MWTaskHistoryEntry,
  MWTaskAttachment,
} from '../../types'

// ── Project kanban tasks (collaborative 5-column board) ──
//
// Backend: server/app/matcha/routes/matcha_work.py (~4243+) +
// services/project_task_service.py. Columns: todo | in_progress | review |
// changes_requested | done. The board renders the same data the desktop
// (werk) KanbanBoardView does — these are the web equivalents of
// MatchaWorkService+Tasks.swift.

export function listProjectTasks(projectId: string) {
  return api.get<MWProjectTask[]>(`/matcha-work/projects/${projectId}/tasks`)
}

export function createProjectTask(projectId: string, body: MWProjectTaskCreate) {
  return api.post<MWProjectTask>(`/matcha-work/projects/${projectId}/tasks`, body)
}

/** Turn a natural-language prompt into a structured ticket draft (no DB write —
 *  the caller reviews/edits, then creates via `createProjectTask`). 50/24h
 *  Redis rate limit per user; gated `require_admin_or_client` server-side. */
export function draftTaskFromPrompt(projectId: string, prompt: string) {
  return api.post<MWTaskDraft>(`/matcha-work/projects/${projectId}/tasks/ai-draft`, { prompt })
}

/**
 * Partial update. Pass ONLY the keys that changed.
 *
 * GOTCHA: the backend treats every present key as a patch instruction and the
 * column validator rejects a `board_column: null` with a 400 — so drag-to-move
 * must send `{ board_column }` alone, never an object spread full of nulls.
 * `MWProjectTaskPatch` is a `Partial<…>` to make that the natural call shape.
 */
export function updateProjectTask(
  projectId: string,
  taskId: string,
  patch: MWProjectTaskPatch,
) {
  return api.patch<MWProjectTask>(`/matcha-work/projects/${projectId}/tasks/${taskId}`, patch)
}

export function deleteProjectTask(projectId: string, taskId: string) {
  return api.delete(`/matcha-work/projects/${projectId}/tasks/${taskId}`)
}

/** Reviewer sends a task back from `review` for changes (note required). */
export function rejectProjectTask(projectId: string, taskId: string, note: string) {
  return api.post<MWProjectTask>(`/matcha-work/projects/${projectId}/tasks/${taskId}/reject`, { note })
}

/** Reviewer approves a task out of `review` → done (optional sign-off note). */
export function approveProjectTask(projectId: string, taskId: string, note?: string) {
  return api.post<MWProjectTask>(`/matcha-work/projects/${projectId}/tasks/${taskId}/approve`, {
    note: note?.trim() ? note : null,
  })
}

// ── Task attachments (files scoped to one card) ──
//
// Distinct from the project-wide files in projects.ts (`uploadProjectFile`):
// these carry `task_id`, so they render on the ticket. Backend caps uploads at
// 10 MB and whitelists extensions (routes/matcha_work/projects.py:518) — mirror
// both client-side so a rejected file fails before the round-trip.

export const TASK_FILE_MAX_BYTES = 10 * 1024 * 1024
export const TASK_FILE_ALLOWED_EXT =
  /\.(pdf|docx?|txt|csv|xlsx?|png|jpe?g|gif|webp|svg|heic|heif|pptx|md)$/i

export function listTaskFiles(projectId: string, taskId: string) {
  return api.get<MWTaskAttachment[]>(`/matcha-work/projects/${projectId}/tasks/${taskId}/files`)
}

export function uploadTaskFile(projectId: string, taskId: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return api.upload<MWTaskAttachment>(
    `/matcha-work/projects/${projectId}/tasks/${taskId}/files`,
    form,
  )
}

export function deleteTaskFile(projectId: string, taskId: string, fileId: string) {
  return api.delete(`/matcha-work/projects/${projectId}/tasks/${taskId}/files/${fileId}`)
}

/** Audit-trail timeline for one task. Used by the "copy for Claude Code"
 *  export to tell a rework apart from a fresh ticket (`review_rejected` /
 *  `subtask_rejected` / `round_started` events). */
export function getTaskHistory(projectId: string, taskId: string) {
  return api.get<MWTaskHistoryEntry[]>(`/matcha-work/projects/${projectId}/tasks/${taskId}/history`)
}

// ── Subtasks (per-card checklist) ──

export function listSubtasks(projectId: string, taskId: string) {
  return api.get<MWSubtask[]>(`/matcha-work/projects/${projectId}/tasks/${taskId}/subtasks`)
}

export function createSubtask(projectId: string, taskId: string, title: string) {
  return api.post<MWSubtask>(`/matcha-work/projects/${projectId}/tasks/${taskId}/subtasks`, { title })
}

/** Toggle one checklist item. Sends only `is_done` so the title/position are
 *  never blanked (backend treats any present key as an edit). */
export function updateSubtask(
  projectId: string,
  taskId: string,
  subtaskId: string,
  patch: Partial<{ is_done: boolean; title: string; assigned_to: string | null }>,
) {
  return api.patch<MWSubtask>(
    `/matcha-work/projects/${projectId}/tasks/${taskId}/subtasks/${subtaskId}`,
    patch,
  )
}

export function deleteSubtask(projectId: string, taskId: string, subtaskId: string) {
  return api.delete<{ deleted: boolean }>(
    `/matcha-work/projects/${projectId}/tasks/${taskId}/subtasks/${subtaskId}`,
  )
}
