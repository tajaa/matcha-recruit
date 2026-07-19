import { useEffect, useRef, useState } from 'react'
import { Check, ClipboardCopy, Copy, Loader2, Trash2, X } from 'lucide-react'
import type { BoardColumn, MWProjectTask } from '../../../types'
import { KANBAN_COLUMNS } from '../../../utils/kanbanColumns'
import { copyTicketToClipboard } from './copyTicket'

interface TaskActionSheetProps {
  projectId: string
  task: MWProjectTask
  onClose: () => void
  onMove: (column: BoardColumn) => void
  onDuplicate: () => Promise<void>
  onDelete: () => void
}

/**
 * Per-card actions, as a bottom sheet on mobile / centered dialog on desktop.
 *
 * This is the touch replacement for drag-to-move: the board's only move
 * affordance was HTML5 drag-and-drop (`onDragStart`/`onDrop`), which does not
 * fire from a finger — so on a phone a card could be read but never moved.
 * "Duplicate" mirrors desktop Werk's `duplicateTask`.
 */
export default function TaskActionSheet({ projectId, task, onClose, onMove, onDuplicate, onDelete }: TaskActionSheetProps) {
  const [duplicating, setDuplicating] = useState(false)
  const [copying, setCopying] = useState(false)
  const [copied, setCopied] = useState(false)
  // The post-copy auto-close is deferred, so it has to be cancellable: the
  // sheet can be dismissed (or its card moved/deleted) inside that window.
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => {
    if (closeTimer.current) clearTimeout(closeTimer.current)
  }, [])

  /** Same export as the detail panel's Copy button, reachable straight from the
   *  card so grabbing a ticket for Claude Code doesn't require opening it. */
  async function handleCopyTicket() {
    if (copying) return
    setCopying(true)
    try {
      await copyTicketToClipboard(projectId, task)
      setCopied(true)
      closeTimer.current = setTimeout(() => {
        setCopied(false)
        onClose()
      }, 900)
    } catch {
      /* clipboard denied */
    } finally {
      setCopying(false)
    }
  }

  async function handleDuplicate() {
    if (duplicating) return
    setDuplicating(true)
    try {
      await onDuplicate()
      onClose()
    } finally {
      setDuplicating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 md:items-center" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-t-2xl border border-w-line bg-w-surface pb-[env(safe-area-inset-bottom)] shadow-2xl md:rounded-2xl"
      >
        <div className="flex items-start gap-2 border-b border-w-line px-4 py-3">
          <p className="min-w-0 flex-1 line-clamp-2 text-sm font-medium text-w-text">{task.title}</p>
          <button onClick={onClose} className="shrink-0 p-1 text-w-dim hover:text-w-text" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-4 py-2">
          <p className="py-1 text-[10px] font-semibold uppercase tracking-wider text-w-dim">Move to</p>
          <div className="flex flex-col">
            {KANBAN_COLUMNS.map((col) => {
              const current = col.key === task.board_column
              return (
                <button
                  key={col.key}
                  disabled={current}
                  onClick={() => {
                    onMove(col.key)
                    onClose()
                  }}
                  className={`flex items-center justify-between rounded-lg px-2 py-2.5 text-left text-sm transition-colors ${
                    current ? 'text-w-accent' : 'text-w-text hover:bg-w-surface2'
                  }`}
                >
                  {col.label}
                  {current && <Check className="h-4 w-4 shrink-0" />}
                </button>
              )
            })}
          </div>
        </div>

        <div className="border-t border-w-line px-4 py-2">
          <button
            onClick={handleCopyTicket}
            disabled={copying}
            className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2.5 text-left text-sm text-w-text transition-colors hover:bg-w-surface2 disabled:opacity-50"
          >
            {copying ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
            ) : copied ? (
              <Check className="h-4 w-4 shrink-0 text-w-accent" />
            ) : (
              <ClipboardCopy className="h-4 w-4 shrink-0" />
            )}
            {copied ? 'Copied' : 'Copy ticket as text'}
          </button>
          <button
            onClick={handleDuplicate}
            disabled={duplicating}
            className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2.5 text-left text-sm text-w-text transition-colors hover:bg-w-surface2 disabled:opacity-50"
          >
            {duplicating ? <Loader2 className="h-4 w-4 shrink-0 animate-spin" /> : <Copy className="h-4 w-4 shrink-0" />}
            Duplicate
          </button>
          <button
            onClick={() => {
              onDelete()
              onClose()
            }}
            className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2.5 text-left text-sm text-red-400 transition-colors hover:bg-red-950/40"
          >
            <Trash2 className="h-4 w-4 shrink-0" />
            Delete
          </button>
        </div>
      </div>
    </div>
  )
}
