import { useState, useEffect } from 'react'
import {
  updateProjectTask,
  rejectProjectTask,
  approveProjectTask,
  listSubtasks,
  createSubtask,
  updateSubtask,
  deleteSubtask,
} from '../../../api/matchaWork'
import type { MWProjectTask, MWSubtask, MWTaskAttachment, BoardColumn, TaskPriority } from '../../../types'
import { copyTicketToClipboard } from './copyTicket'

interface UseTaskDetailPanelArgs {
  projectId: string
  task: MWProjectTask
  onPatched: (updated: MWProjectTask) => void
  onSubtaskCountChange: (total: number, done: number) => void
}

export function useTaskDetailPanel({
  projectId,
  task,
  onPatched,
  onSubtaskCountChange,
}: UseTaskDetailPanelArgs) {
  // Mirrored locally so the clipboard export picks up a screenshot attached
  // seconds ago, without waiting for the board to refetch the task row.
  const [attachments, setAttachments] = useState<MWTaskAttachment[]>(task.attachments ?? [])
  const [duplicating, setDuplicating] = useState(false)
  const [copying, setCopying] = useState(false)
  const [copied, setCopied] = useState(false)
  const [subtasks, setSubtasks] = useState<MWSubtask[]>([])
  const [subtasksLoading, setSubtasksLoading] = useState(true)
  const [newSubtask, setNewSubtask] = useState('')
  const [savingField, setSavingField] = useState(false)

  // Review send-back / approve — only surfaced while the card sits in Review.
  const [showRejectNote, setShowRejectNote] = useState(false)
  const [rejectNote, setRejectNote] = useState('')
  const [reviewBusy, setReviewBusy] = useState(false)

  async function handleApprove() {
    setReviewBusy(true)
    try {
      const updated = await approveProjectTask(projectId, task.id)
      onPatched(updated)
    } catch {
      /* surfaced via the board's own error path */
    } finally {
      setReviewBusy(false)
    }
  }

  async function handleReject() {
    const note = rejectNote.trim()
    if (!note || reviewBusy) return
    setReviewBusy(true)
    try {
      const updated = await rejectProjectTask(projectId, task.id, note)
      onPatched(updated)
      setShowRejectNote(false)
      setRejectNote('')
    } catch {
      /* surfaced via the board's own error path */
    } finally {
      setReviewBusy(false)
    }
  }

  // Local editable copies of the inline fields.
  const [description, setDescription] = useState(task.description ?? '')

  useEffect(() => {
    setDescription(task.description ?? '')
  }, [task.id, task.description])

  useEffect(() => {
    let active = true
    setSubtasksLoading(true)
    listSubtasks(projectId, task.id)
      .then((rows) => {
        if (active) setSubtasks(rows)
      })
      .catch(() => {})
      .finally(() => {
        if (active) setSubtasksLoading(false)
      })
    return () => {
      active = false
    }
  }, [projectId, task.id])

  function reportCounts(rows: MWSubtask[]) {
    onSubtaskCountChange(rows.length, rows.filter((s) => s.is_done).length)
  }

  async function patchField(patch: Partial<{ priority: TaskPriority; description: string | null; board_column: BoardColumn }>) {
    setSavingField(true)
    try {
      const updated = await updateProjectTask(projectId, task.id, patch)
      onPatched(updated)
    } catch {
      /* surfaced on the board via its own error path on reload; keep panel quiet */
    } finally {
      setSavingField(false)
    }
  }

  /**
   * Copy the ticket to the clipboard as one markdown blob tuned for Claude Code
   * — title, description, progress, checklist, attachments, screenshot URLs,
   * and (when the card was sent back) the reviewer's changes-requested brief.
   * Mirrors desktop Werk's Copy button on the task viewer sheet.
   *
   * Disabled until the checklist has loaded: copying mid-fetch would export an
   * empty checklist and, worse, make deriveReviewContext read currentRound as 1
   * from the empty list — silently mislabelling a round-3 rework brief.
   */
  async function handleCopyTicket() {
    if (copying || subtasksLoading) return
    setCopying(true)
    try {
      await copyTicketToClipboard(projectId, { ...task, attachments }, subtasks)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard denied — nothing useful to say in the panel */
    } finally {
      setCopying(false)
    }
  }

  async function addSubtask() {
    const title = newSubtask.trim()
    if (!title) return
    try {
      const created = await createSubtask(projectId, task.id, title)
      const next = [...subtasks, created]
      setSubtasks(next)
      reportCounts(next)
      setNewSubtask('')
    } catch {
      /* ignore — input retains the text for retry */
    }
  }

  async function toggleSubtask(sub: MWSubtask) {
    const next = subtasks.map((s) => (s.id === sub.id ? { ...s, is_done: !s.is_done } : s))
    setSubtasks(next)
    reportCounts(next)
    try {
      await updateSubtask(projectId, task.id, sub.id, { is_done: !sub.is_done })
    } catch {
      // Revert on failure.
      const reverted = subtasks.map((s) => (s.id === sub.id ? { ...s, is_done: sub.is_done } : s))
      setSubtasks(reverted)
      reportCounts(reverted)
    }
  }

  async function removeSubtask(sub: MWSubtask) {
    const next = subtasks.filter((s) => s.id !== sub.id)
    setSubtasks(next)
    reportCounts(next)
    try {
      await deleteSubtask(projectId, task.id, sub.id)
    } catch {
      setSubtasks(subtasks)
      reportCounts(subtasks)
    }
  }

  return {
    attachments,
    setAttachments,
    duplicating,
    setDuplicating,
    copying,
    copied,
    subtasks,
    subtasksLoading,
    newSubtask,
    setNewSubtask,
    savingField,
    showRejectNote,
    setShowRejectNote,
    rejectNote,
    setRejectNote,
    reviewBusy,
    handleApprove,
    handleReject,
    description,
    setDescription,
    patchField,
    handleCopyTicket,
    addSubtask,
    toggleSubtask,
    removeSubtask,
  }
}
