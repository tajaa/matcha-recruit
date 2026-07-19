import type { MWProjectTask, MWSubtask, MWTaskAttachment, MWTaskHistoryEntry } from '../types'

/**
 * Builds a clipboard-friendly markdown blob describing a task, so the ticket
 * can be dropped straight into Claude Code / Codex / any chat that takes
 * markdown. Web port of the desktop `TaskClipboardExporter`
 * (platforms/desktop/Werk/.../TaskViewer/TaskClipboardExporter.swift) — keep
 * the two in sync.
 *
 * Deliberately content-only (title, description, progress, checklist,
 * attachments, screenshots): the project-management metadata (status,
 * priority, assignee, due date) is omitted because it's noise to a coding
 * agent acting on the ticket.
 *
 * ONE INTENDED DIVERGENCE FROM DESKTOP — screenshots. Desktop downloads the
 * images to a temp dir and emits LOCAL file paths, because a macOS app can
 * write files and a CLI can't fetch a URL it isn't given. A browser can't
 * write to the filesystem at all, so we emit the CloudFront URLs instead.
 * These objects are served unauthenticated (verified: a task image URL returns
 * 200 with no credentials), so an agent can fetch them and the user can click
 * them — which makes the URL the *better* medium here, not a degradation.
 *
 * A ticket sent back from review is the exception to the whole shape: there the
 * review IS the content. Pass a `review` context and the blob is reshaped into
 * a rework brief — the directive and the rejection lead, the original ticket
 * demotes to supporting context.
 */

/** One checklist item the reviewer rejected, with why and how badly. Comes from
 *  a `subtask_rejected` history event's metadata, not from the subtask row —
 *  reason and severity are stored nowhere else. */
export interface TaskDenial {
  title: string
  reason: string
  severity: string
}

/** What a coding agent needs in order to read the ticket as a REWORK. */
export interface TaskReviewContext {
  note: string
  denials: TaskDenial[]
  /** "2 blockers · 1 nit", or null when no denial carried a severity. */
  severitySummary: string | null
  currentRound: number
  totalRounds: number
  /** Times this ticket has been sent back. 0 when the server didn't say. */
  cycleCount: number
  sentBackBy: string | null
  /** ISO8601 timestamp of the latest `review_rejected` event. */
  sentBackAt: string | null
  /** Titles completed in each earlier round, oldest round first. */
  fixedEarlier: { round: number; titles: string[] }[]
}

/** Binary units, matching the desktop exporter's `formatSize`. Exported so the
 *  attachments panel and the clipboard blob can't disagree about the size of
 *  the same file (they did: one used 1000-based, the other 1024-based). */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** THE image predicate for task attachments. Exported so the card thumbnail
 *  strip, the panel grid, and the export all classify a file identically. */
export function isImage(a: MWTaskAttachment): boolean {
  return (a.content_type ?? '').startsWith('image/')
}

function ordinal(n: number): string {
  if ([11, 12, 13].includes(n % 100)) return `${n}th`
  switch (n % 10) {
    case 1: return `${n}st`
    case 2: return `${n}nd`
    case 3: return `${n}rd`
    default: return `${n}th`
  }
}

/** "Sent back by Jane Doe on Jul 7, 2026 (3rd send-back) — 2 blockers · 1 nit".
 *  Every clause is optional; null when none are known, since a bare "Sent back"
 *  says nothing the directive above hasn't already said. */
function attributionLine(review: TaskReviewContext): string | null {
  let head = 'Sent back'
  let known = false
  if (review.sentBackBy) {
    head += ` by ${review.sentBackBy}`
    known = true
  }
  if (review.sentBackAt) {
    const d = new Date(review.sentBackAt)
    if (!Number.isNaN(d.getTime())) {
      head += ` on ${d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`
      known = true
    }
  }
  // "1st send-back" is just "sent back" — only worth saying once it repeats.
  if (review.cycleCount > 1) {
    head += ` (${ordinal(review.cycleCount)} send-back)`
    known = true
  }
  if (review.severitySummary) {
    head += ` — ${review.severitySummary}`
    known = true
  }
  return known ? head : null
}

/** The rework header: a directive naming this as a send-back, the reviewer's
 *  note and rejected items, this round's checklist, and what earlier rounds
 *  already fixed. All of it precedes the original brief. */
function appendRework(review: TaskReviewContext, subtasks: MWSubtask[], lines: string[]) {
  const round = review.totalRounds > 1 ? `You are on round ${review.currentRound} of ${review.totalRounds}. ` : ''
  const dontRedo = review.fixedEarlier.length === 0 ? '' : ' Do not re-do items listed under "Already fixed".'
  lines.push(
    '> **Task for you:** This ticket was reviewed and sent back for changes. ' +
      round +
      'Address the changes requested below. The original brief and earlier rounds are context, not new work.' +
      dontRedo,
  )
  lines.push('')

  lines.push('## Changes requested')
  const attribution = attributionLine(review)
  if (attribution) {
    lines.push(attribution)
    lines.push('')
  }
  // Blockquote the reviewer's own words so a multi-line note can't be read as
  // part of the surrounding instructions.
  for (const line of review.note.split('\n')) lines.push(`> ${line}`)
  lines.push('')

  for (const d of review.denials) {
    const tag = d.severity ? `**[${d.severity}]** ` : ''
    const reason = d.reason ? ` — ${d.reason}` : ''
    lines.push(`- ${tag}${d.title}${reason}`)
  }
  if (review.denials.length > 0) lines.push('')

  if (subtasks.length > 0) {
    const done = subtasks.filter((s) => s.is_done).length
    lines.push(`## Open checklist (round ${review.currentRound}, ${done}/${subtasks.length} done)`)
    for (const s of [...subtasks].sort((a, b) => a.position - b.position)) {
      lines.push(`- [${s.is_done ? 'x' : ' '}] ${s.title}`)
    }
    lines.push('')
  }

  if (review.fixedEarlier.length > 0) {
    lines.push('## Already fixed in earlier rounds')
    for (const r of review.fixedEarlier) {
      for (const title of r.titles) lines.push(`- Round ${r.round}: ${title}`)
    }
    lines.push('')
  }
}

export function taskMarkdown({
  task,
  attachments = [],
  subtasks = [],
  review = null,
}: {
  task: MWProjectTask
  attachments?: MWTaskAttachment[]
  subtasks?: MWSubtask[]
  review?: TaskReviewContext | null
}): string {
  const lines: string[] = []
  lines.push(`# ${task.title}`)
  lines.push('')

  if (review) appendRework(review, subtasks, lines)

  // On a rework the brief is context, not the ask — retitle it and let the
  // changes requested sit above it.
  lines.push(review === null ? '## Description' : '## The brief (original ticket)')
  const description = (task.description ?? '').trim()
  lines.push(description || '_(no description)_')
  lines.push('')

  lines.push("## Where We're At")
  const progress = (task.progress_note ?? '').trim()
  lines.push(progress || '_(no progress note)_')
  lines.push('')

  // The rework path already printed the checklist, scoped to its round.
  if (subtasks.length > 0 && review === null) {
    const done = subtasks.filter((s) => s.is_done).length
    lines.push(`## Checklist (${done}/${subtasks.length})`)
    for (const s of [...subtasks].sort((a, b) => a.position - b.position)) {
      lines.push(`- [${s.is_done ? 'x' : ' '}] ${s.title}`)
    }
    lines.push('')
  }

  const nonImages = attachments.filter((a) => !isImage(a))
  if (nonImages.length > 0) {
    lines.push(`## Attachments (${nonImages.length})`)
    for (const f of nonImages) lines.push(`- ${f.filename} — ${formatSize(f.file_size)}`)
    lines.push('')
  }

  // Cap at 6, matching desktop — a ticket with a dozen screenshots would bury
  // the brief under URLs.
  const images = attachments.filter(isImage).slice(0, 6)
  if (images.length > 0) {
    lines.push('## Screenshots')
    lines.push('_Fetch these URLs to view:_')
    for (const img of images) lines.push(img.storage_url)
    lines.push('')
  }

  return lines.join('\n')
}

/**
 * Derive the review context from the task + its history, mirroring desktop's
 * `TaskViewerSheet.reviewContext`.
 *
 * The gate deliberately isn't `board_column === 'changes_requested'`: rejecting
 * lands the card there, but `review_note` survives the assignee dragging it to
 * In Progress to start the rework — which is exactly when they'd copy it. The
 * server clears the note on re-entry to review/done, so the note's presence is
 * the truth.
 */
export function deriveReviewContext(
  task: MWProjectTask,
  history: MWTaskHistoryEntry[],
  allSubtasks: MWSubtask[],
): TaskReviewContext | null {
  const note = (task.review_note ?? '').trim()
  if (!note || !['changes_requested', 'in_progress', 'todo'].includes(task.board_column)) return null

  // Round = highest round_index among the subtasks (defaults to 1), same as
  // desktop — derived from the subtasks so it's right without the history.
  const currentRound = allSubtasks.reduce((max, s) => Math.max(max, s.round_index ?? 1), 1)

  // `round_started` count → total rounds. (Anything created at/after the k-th
  // boundary belongs to round k+1 — the same derivation the backend uses.)
  const boundaries = history.filter((h) => h.event_type === 'round_started').map((h) => h.created_at)

  const sentBack = [...history].reverse().find((h) => h.event_type === 'review_rejected') ?? null

  // Latest rejection per still-open checklist item.
  const openIds = new Set(allSubtasks.filter((s) => !s.is_done).map((s) => s.id))
  const latest = new Map<string, MWTaskHistoryEntry>()
  for (const e of history) {
    if (e.event_type !== 'subtask_rejected') continue
    const sid = e.metadata?.subtask_id
    if (typeof sid !== 'string' || !openIds.has(sid)) continue
    const prev = latest.get(sid)
    if (prev && prev.created_at >= e.created_at) continue
    latest.set(sid, e)
  }
  const denials: TaskDenial[] = [...latest.values()]
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
    .map((e) => ({
      title: typeof e.metadata?.title === 'string' ? e.metadata.title : 'Item',
      reason: typeof e.metadata?.reason === 'string' ? e.metadata.reason : '',
      severity: typeof e.metadata?.severity === 'string' ? e.metadata.severity : '',
    }))

  const blockers = denials.filter((d) => d.severity === 'blocker').length
  const nits = denials.filter((d) => d.severity === 'nit').length
  const severityParts: string[] = []
  if (blockers > 0) severityParts.push(`${blockers} blocker${blockers === 1 ? '' : 's'}`)
  if (nits > 0) severityParts.push(`${nits} nit${nits === 1 ? '' : 's'}`)

  // Everything closed before the current round: work the reviewer already
  // accepted. Listing it is what stops the agent rebuilding it.
  const fixedEarlier: { round: number; titles: string[] }[] = []
  for (let r = 1; r < currentRound; r++) {
    const titles = allSubtasks.filter((s) => (s.round_index ?? 1) === r && s.is_done).map((s) => s.title)
    if (titles.length > 0) fixedEarlier.push({ round: r, titles })
  }

  const totalRounds = Math.max(boundaries.length + 1, currentRound)

  return {
    note,
    denials,
    severitySummary: severityParts.length > 0 ? severityParts.join(' · ') : null,
    currentRound,
    totalRounds,
    cycleCount: task.review_cycle_count ?? 0,
    sentBackBy: sentBack?.actor_name ?? null,
    sentBackAt: sentBack?.created_at ?? null,
    fixedEarlier,
  }
}
