import { Loader2, X, Search, LayoutGrid, List } from 'lucide-react'
import TaskProgressBar from './TaskProgressBar'
import AiDraftBar from './AiDraftBar'
import AiDraftReviewModal from './AiDraftReviewModal'
import TemplateComposeModal from './TemplateComposeModal'
import KanbanListView from './KanbanListView'
import { KANBAN_COLUMNS } from '../../utils/kanbanColumns'
import { useKanbanBoard } from './ProjectKanbanBoard/useKanbanBoard'
import KanbanColumn from './ProjectKanbanBoard/KanbanColumn'
import TaskDetailPanel from './ProjectKanbanBoard/TaskDetailPanel'
import TaskActionSheet from './ProjectKanbanBoard/TaskActionSheet'
import { useIsDesktop } from '../../hooks/useMediaQuery'

interface ProjectKanbanBoardProps {
  projectId: string
}

export default function ProjectKanbanBoard({ projectId }: ProjectKanbanBoardProps) {
  const {
    tasks,
    setTasks,
    loading,
    error,
    setError,
    draggingId,
    setDraggingId,
    dragOverColumn,
    setDragOverColumn,
    addingColumn,
    setAddingColumn,
    newTitle,
    setNewTitle,
    creating,
    setSelectedId,
    searchText,
    setSearchText,
    showList,
    setShowList,
    doneExpanded,
    setDoneExpanded,
    hoveredEmptyColumn,
    setHoveredEmptyColumn,
    menuColumn,
    setMenuColumn,
    menuRef,
    templateCompose,
    setTemplateCompose,
    aiDrafting,
    aiError,
    aiDraft,
    setAiDraft,
    collaborators,
    modalBusy,
    changedIds,
    me,
    selectedTask,
    tokens,
    visible,
    canAiDraft,
    ensureCollaborators,
    acknowledge,
    moveTask,
    handleCreate,
    handleDelete,
    patchLocal,
    handleAiDraft,
    handleCreateFromPayload,
    setActionTaskId,
    actionTask,
    mobileColumn,
    setMobileColumn,
    duplicateTask,
  } = useKanbanBoard(projectId)
  const isDesktop = useIsDesktop()

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-w-dim" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {error && (
        <div className="mx-4 mt-3 flex items-center justify-between rounded-lg border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-300">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-200">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {tasks.length > 0 && (
        <div className="flex items-center gap-2 px-3 pt-3">
          <Search className="h-3.5 w-3.5 shrink-0 text-w-dim" />
          <input
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Search tasks…"
            title='space = AND, "quotes" = exact phrase'
            className="min-w-0 flex-1 bg-transparent text-[13px] text-w-text placeholder-w-faint outline-none"
          />
          {searchText && (
            <button onClick={() => setSearchText('')} className="shrink-0 text-w-dim hover:text-w-text">
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}

      {tasks.length > 0 && <TaskProgressBar tasks={tasks} />}

      <div className="flex items-center gap-1 px-3 pb-2">
        <button
          onClick={() => {
            setShowList(false)
            localStorage.setItem('mw-kanban-list-layout', '0')
          }}
          className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium transition-colors ${
            !showList ? 'bg-w-accent/15 text-w-accent' : 'text-w-dim hover:text-w-text'
          }`}
        >
          <LayoutGrid className="h-3 w-3" />
          Board
        </button>
        <button
          onClick={() => {
            setShowList(true)
            localStorage.setItem('mw-kanban-list-layout', '1')
          }}
          className={`flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium transition-colors ${
            showList ? 'bg-w-accent/15 text-w-accent' : 'text-w-dim hover:text-w-text'
          }`}
        >
          <List className="h-3 w-3" />
          List
        </button>
      </div>

      {canAiDraft && <AiDraftBar drafting={aiDrafting} error={aiError} onDraft={handleAiDraft} />}

      {showList ? (
        <KanbanListView
          tasks={visible}
          searchTokens={tokens}
          myUserId={me?.user.id ?? null}
          changedIds={changedIds}
          onOpen={(t) => {
            acknowledge(t.id)
            setSelectedId(t.id)
          }}
          onMenu={setActionTaskId}
        />
      ) : (
        <>
        {/* Below `md`, one column at a time behind a pager. Five 85vw columns in
            a snap-scroller meant hunting sideways for a lane, and cards could
            not be moved at all (drag-and-drop is HTML5-only — see
            TaskActionSheet).

            Exactly ONE of the two layouts is mounted, chosen in JS rather than
            by `hidden md:flex`: two KanbanColumns per lane would share the
            single `menuRef`, the later one would win it, and the visible
            column's "+" menu would close on mousedown before its buttons
            fired. */}
        {!isDesktop && (
          <div className="flex shrink-0 gap-1 overflow-x-auto px-2.5 pb-1.5">
            {KANBAN_COLUMNS.map((col) => {
              const count = visible.filter((t) => t.board_column === col.key).length
              const active = mobileColumn === col.key
              return (
                <button
                  key={col.key}
                  onClick={() => setMobileColumn(col.key)}
                  className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-medium transition-colors ${
                    active ? 'bg-w-accent/15 text-w-accent' : 'text-w-dim hover:text-w-text'
                  }`}
                >
                  {col.label}
                  <span className={`rounded-full px-1.5 text-[10px] ${active ? 'bg-w-accent/20' : 'bg-w-surface2'}`}>
                    {count}
                  </span>
                </button>
              )
            })}
          </div>
        )}

        <div className={isDesktop ? 'flex flex-1 gap-2 overflow-x-auto p-2.5' : 'flex min-h-0 flex-1 p-2.5 pt-0'}>
          {(isDesktop ? KANBAN_COLUMNS : KANBAN_COLUMNS.filter((c) => c.key === mobileColumn)).map((col) => (
            <KanbanColumn
              key={col.key}
              col={col}
              singleColumn={!isDesktop}
              onCardMenu={setActionTaskId}
              visible={visible}
              doneExpanded={doneExpanded}
              setDoneExpanded={setDoneExpanded}
              dragOverColumn={dragOverColumn}
              setDragOverColumn={setDragOverColumn}
              draggingId={draggingId}
              setDraggingId={setDraggingId}
              hoveredEmptyColumn={hoveredEmptyColumn}
              setHoveredEmptyColumn={setHoveredEmptyColumn}
              addingColumn={addingColumn}
              setAddingColumn={setAddingColumn}
              newTitle={newTitle}
              setNewTitle={setNewTitle}
              creating={creating}
              menuColumn={menuColumn}
              setMenuColumn={setMenuColumn}
              menuRef={menuRef}
              changedIds={changedIds}
              moveTask={moveTask}
              handleCreate={handleCreate}
              ensureCollaborators={ensureCollaborators}
              setTemplateCompose={setTemplateCompose}
              acknowledge={acknowledge}
              setSelectedId={setSelectedId}
            />
          ))}
        </div>
        </>
      )}

      {actionTask && (
        <TaskActionSheet
          projectId={projectId}
          task={actionTask}
          onClose={() => setActionTaskId(null)}
          onMove={(col) => moveTask(actionTask.id, col)}
          onDuplicate={() => duplicateTask(actionTask.id)}
          onDelete={() => handleDelete(actionTask.id)}
        />
      )}

      {selectedTask && (
        <TaskDetailPanel
          key={selectedTask.id}
          projectId={projectId}
          task={selectedTask}
          onClose={() => setSelectedId(null)}
          onPatched={(updated) => patchLocal(selectedTask.id, updated)}
          onDelete={() => handleDelete(selectedTask.id)}
          onDuplicate={() => duplicateTask(selectedTask.id)}
          onAttachmentsChange={(files) =>
            setTasks((prev) =>
              prev.map((t) => (t.id === selectedTask.id ? { ...t, attachments: files } : t)),
            )
          }
          onSubtaskCountChange={(total, done) =>
            setTasks((prev) =>
              prev.map((t) =>
                t.id === selectedTask.id ? { ...t, subtask_total: total, subtask_done: done } : t,
              ),
            )
          }
        />
      )}

      {aiDraft && (
        <AiDraftReviewModal
          draft={aiDraft}
          collaborators={collaborators}
          busy={modalBusy}
          onCreate={handleCreateFromPayload}
          onClose={() => setAiDraft(null)}
        />
      )}

      {templateCompose && (
        <TemplateComposeModal
          template={templateCompose.template}
          column={templateCompose.column}
          collaborators={collaborators}
          busy={modalBusy}
          onCreate={handleCreateFromPayload}
          onClose={() => setTemplateCompose(null)}
        />
      )}
    </div>
  )
}
