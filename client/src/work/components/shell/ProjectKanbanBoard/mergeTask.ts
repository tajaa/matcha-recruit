import type { MWProjectTask } from '../../../types'

// Preserve the list-only aggregate fields a PATCH/create RETURNING clause omits
// (they'd otherwise be clobbered to undefined when merging the server row).
export function mergeTask(local: MWProjectTask, server: MWProjectTask): MWProjectTask {
  return {
    ...server,
    subtask_total: server.subtask_total ?? local.subtask_total,
    subtask_done: server.subtask_done ?? local.subtask_done,
    review_cycle_count: server.review_cycle_count ?? local.review_cycle_count,
    last_moved_at: server.last_moved_at ?? local.last_moved_at,
    assigned_name: server.assigned_name ?? local.assigned_name,
    assigned_email: server.assigned_email ?? local.assigned_email,
    element_name: server.element_name ?? local.element_name,
    attachments: server.attachments ?? local.attachments,
  }
}
