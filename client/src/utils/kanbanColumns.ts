import type { BoardColumn } from '../types/matcha-work'

/** Board lane order — matches the desktop `kanbanColumns` (todo → in_progress
 *  → review → changes_requested → done). Shared by the board and list views
 *  so both group tasks identically. */
export const KANBAN_COLUMNS: { key: BoardColumn; label: string }[] = [
  { key: 'todo', label: 'Todo' },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'review', label: 'Review' },
  { key: 'changes_requested', label: 'Changes Requested' },
  { key: 'done', label: 'Done' },
]
