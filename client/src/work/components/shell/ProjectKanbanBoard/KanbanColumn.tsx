import type { Dispatch, SetStateAction } from 'react'
import { Plus } from 'lucide-react'
import type { MWProjectTask, BoardColumn } from '../../../types'
import { KANBAN_TEMPLATES, type KanbanTemplate } from '../../../utils/kanbanTemplates'
import KanbanCard from '../KanbanCard'
import AddCardInput from './AddCardInput'

interface KanbanColumnProps {
  col: { key: BoardColumn; label: string }
  visible: MWProjectTask[]
  doneExpanded: boolean
  setDoneExpanded: Dispatch<SetStateAction<boolean>>
  dragOverColumn: BoardColumn | null
  setDragOverColumn: Dispatch<SetStateAction<BoardColumn | null>>
  draggingId: string | null
  setDraggingId: Dispatch<SetStateAction<string | null>>
  hoveredEmptyColumn: BoardColumn | null
  setHoveredEmptyColumn: Dispatch<SetStateAction<BoardColumn | null>>
  addingColumn: BoardColumn | null
  setAddingColumn: Dispatch<SetStateAction<BoardColumn | null>>
  newTitle: string
  setNewTitle: Dispatch<SetStateAction<string>>
  creating: boolean
  menuColumn: BoardColumn | null
  setMenuColumn: Dispatch<SetStateAction<BoardColumn | null>>
  menuRef: React.RefObject<HTMLDivElement | null>
  changedIds: Set<string>
  moveTask: (taskId: string, toColumn: BoardColumn) => void
  handleCreate: (column: BoardColumn) => void
  ensureCollaborators: () => void
  setTemplateCompose: Dispatch<SetStateAction<{ template: KanbanTemplate; column: BoardColumn } | null>>
  acknowledge: (taskId: string) => void
  setSelectedId: Dispatch<SetStateAction<string | null>>
}

export default function KanbanColumn({
  col,
  visible,
  doneExpanded,
  setDoneExpanded,
  dragOverColumn,
  setDragOverColumn,
  draggingId,
  setDraggingId,
  hoveredEmptyColumn,
  setHoveredEmptyColumn,
  addingColumn,
  setAddingColumn,
  newTitle,
  setNewTitle,
  creating,
  menuColumn,
  setMenuColumn,
  menuRef,
  changedIds,
  moveTask,
  handleCreate,
  ensureCollaborators,
  setTemplateCompose,
  acknowledge,
  setSelectedId,
}: KanbanColumnProps) {
  let colTasks = visible.filter((t) => t.board_column === col.key)
  if (col.key === 'done') {
    colTasks = [...colTasks].sort((a, b) => (b.completed_at ?? '').localeCompare(a.completed_at ?? ''))
  }
  const totalInColumn = colTasks.length
  const shownTasks = col.key === 'done' && !doneExpanded && totalInColumn > 5 ? colTasks.slice(0, 5) : colTasks
  const isEmpty = totalInColumn === 0
  const isDropTarget = dragOverColumn === col.key
  const collapsed =
    isEmpty && addingColumn !== col.key && hoveredEmptyColumn !== col.key && !isDropTarget

  return (
    <div
      onMouseEnter={() => {
        if (isEmpty) setHoveredEmptyColumn(col.key)
      }}
      onMouseLeave={() => setHoveredEmptyColumn((c) => (c === col.key ? null : c))}
      onDragOver={(e) => {
        e.preventDefault()
        if (dragOverColumn !== col.key) setDragOverColumn(col.key)
      }}
      onDragLeave={(e) => {
        // Only clear when the pointer actually leaves the column subtree.
        if (!e.currentTarget.contains(e.relatedTarget as Node)) {
          setDragOverColumn((c) => (c === col.key ? null : c))
        }
      }}
      onDrop={(e) => {
        e.preventDefault()
        setDragOverColumn(null)
        if (draggingId) moveTask(draggingId, col.key)
      }}
      className={`flex shrink-0 flex-col rounded-lg border bg-w-surface transition-[width] duration-150 ease-out max-md:w-[85vw] max-md:snap-center ${
        collapsed ? 'w-[136px]' : 'w-[240px]'
      } ${isDropTarget ? 'border-w-accent/60 bg-w-accent/10' : 'border-w-line'}`}
    >
      {/* Column header */}
      <div className="relative flex items-center justify-between gap-1.5 px-2.5 py-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="min-w-0 truncate whitespace-nowrap text-[10px] font-semibold uppercase tracking-wider text-w-dim" title={col.label}>
            {col.label}
          </span>
          <span className="shrink-0 rounded bg-w-surface2 px-1.5 py-0.5 text-[10px] text-w-dim">
            {totalInColumn}
          </span>
        </div>
        <button
          onClick={() => setMenuColumn((c) => (c === col.key ? null : col.key))}
          className="shrink-0 text-w-dim transition-colors hover:text-w-text"
          title="Add card"
        >
          <Plus className="h-4 w-4" />
        </button>

        {menuColumn === col.key && (
          <div
            ref={menuRef}
            className="absolute right-0 top-full z-20 mt-1 w-44 rounded-lg border border-w-line bg-w-surface py-1 shadow-xl"
          >
            <button
              onClick={() => {
                setAddingColumn(col.key)
                setNewTitle('')
                setMenuColumn(null)
              }}
              className="block w-full px-3 py-1.5 text-left text-xs text-w-text hover:bg-w-surface2"
            >
              Blank task
            </button>
            <div className="my-1 border-t border-w-line" />
            {KANBAN_TEMPLATES.map((t) => {
              const TIcon = t.icon
              return (
                <button
                  key={t.key}
                  onClick={() => {
                    ensureCollaborators()
                    setTemplateCompose({ template: t, column: col.key })
                    setMenuColumn(null)
                  }}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-w-text hover:bg-w-surface2"
                >
                  <TIcon className={`h-3.5 w-3.5 shrink-0 ${t.colorClass}`} />
                  {t.displayName}
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* Cards — collapsed empty columns show header only */}
      {!collapsed && (
        <div className="flex flex-1 flex-col gap-2 px-2 pb-2 min-h-0 max-md:overflow-y-auto">
          {addingColumn === col.key && (
            <AddCardInput
              value={newTitle}
              onChange={setNewTitle}
              onSubmit={() => handleCreate(col.key)}
              onCancel={() => {
                setAddingColumn(null)
                setNewTitle('')
              }}
              busy={creating}
            />
          )}

          {shownTasks.map((task) => (
            <KanbanCard
              key={task.id}
              task={task}
              ringed={changedIds.has(task.id)}
              dragging={draggingId === task.id}
              onClick={() => {
                acknowledge(task.id)
                setSelectedId(task.id)
              }}
              onDragStart={(e) => {
                setDraggingId(task.id)
                e.dataTransfer.effectAllowed = 'move'
                // Some browsers require data to be set for a drag to start.
                e.dataTransfer.setData('text/plain', task.id)
              }}
              onDragEnd={() => {
                setDraggingId(null)
                setDragOverColumn(null)
              }}
            />
          ))}

          {col.key === 'done' && totalInColumn > 5 && (
            <button
              onClick={() => setDoneExpanded((v) => !v)}
              className="w-full rounded bg-w-surface2/60 py-1 text-[10px] font-medium text-w-dim transition-colors hover:text-w-text"
            >
              {doneExpanded ? 'Show less' : `Show ${totalInColumn - 5} more`}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
