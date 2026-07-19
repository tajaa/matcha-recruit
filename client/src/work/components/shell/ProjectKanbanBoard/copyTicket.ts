import { listSubtasks, getTaskHistory } from '../../../api/matchaWork'
import type { MWProjectTask, MWSubtask } from '../../../types'
import { taskMarkdown, deriveReviewContext } from '../../../utils/taskClipboard'

/**
 * Assemble a ticket's Claude-Code markdown and put it on the clipboard.
 *
 * Lives here rather than in `utils/taskClipboard` because it does IO, and that
 * module is a pure formatter (`client/CLAUDE.md`: `utils/` is "Pure
 * utilities"). Shared by both entry points — the card's ⋯ action sheet and the
 * detail panel's header button — so the export can't drift between them; the
 * round-filtering rule below is subtle enough that two copies would.
 *
 * @param subtasks  Pass them when the caller already has them (the detail panel
 *   loads them on open); omitted, they're fetched.
 */
export async function copyTicketToClipboard(
  projectId: string,
  task: MWProjectTask,
  subtasks?: MWSubtask[],
): Promise<void> {
  // `deriveReviewContext` returns null unless review_note is set, and that
  // field is already on the board row — so for a ticket that was never sent
  // back, the history request cannot change the output. Skip it.
  const needsHistory = !!task.review_note?.trim()

  const [loadedSubtasks, history] = await Promise.all([
    subtasks ? Promise.resolve(subtasks) : listSubtasks(projectId, task.id).catch(() => []),
    needsHistory ? getTaskHistory(projectId, task.id).catch(() => []) : Promise.resolve([]),
  ])

  const review = deriveReviewContext(task, history, loadedSubtasks)
  const markdown = taskMarkdown({
    task,
    attachments: task.attachments ?? [],
    // Only the current round's checklist is live; earlier rounds are archived
    // and surface through the review context's "already fixed" section.
    subtasks: review
      ? loadedSubtasks.filter((s) => (s.round_index ?? 1) === review.currentRound)
      : loadedSubtasks,
    review,
  })
  await navigator.clipboard.writeText(markdown)
}
