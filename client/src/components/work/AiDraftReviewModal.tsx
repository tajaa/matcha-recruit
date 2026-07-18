import { useState } from 'react'
import { Sparkles, X, Loader2, Plus, ListChecks } from 'lucide-react'
import type {
  MWTaskDraft,
  MWProjectTaskCreate,
  ProjectCollaborator,
  BoardColumn,
  TaskPriority,
} from '../../types/matcha-work'
import { KANBAN_COLUMNS } from '../../utils/kanbanColumns'

const PRIORITIES: TaskPriority[] = ['critical', 'high', 'medium', 'low']
const CATEGORIES = ['manual', 'engineering', 'bug', 'product', 'sales', 'general', 'feat', 'fix']

interface AiDraftReviewModalProps {
  draft: MWTaskDraft
  collaborators: ProjectCollaborator[]
  busy: boolean
  onCreate: (payload: MWProjectTaskCreate) => void
  onClose: () => void
}

export default function AiDraftReviewModal({ draft, collaborators, busy, onCreate, onClose }: AiDraftReviewModalProps) {
  const [title, setTitle] = useState(draft.title)
  const [description, setDescription] = useState(draft.description ?? '')
  const [priority, setPriority] = useState<TaskPriority>(draft.priority)
  const [category, setCategory] = useState(draft.category)
  const [boardColumn, setBoardColumn] = useState<BoardColumn>(draft.board_column)
  const [assignedTo, setAssignedTo] = useState<string>(draft.assigned_to ?? '')
  const [steps, setSteps] = useState<string[]>(draft.subtasks ?? [])
  const [newStep, setNewStep] = useState('')

  function addStep() {
    const t = newStep.trim()
    if (!t) return
    setSteps((prev) => [...prev, t])
    setNewStep('')
  }

  function handleCreate() {
    const t = title.trim()
    if (!t || busy) return
    const cleanedSteps = steps.map((s) => s.trim()).filter(Boolean)
    onCreate({
      title: t,
      board_column: boardColumn,
      priority,
      description: description.trim() ? description.trim() : null,
      category,
      assigned_to: assignedTo || null,
      subtasks: cleanedSteps.length ? cleanedSteps : undefined,
    })
  }

  return (
    <>
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
        <div
          className="w-full max-w-md rounded-xl border border-w-line bg-w-bg shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center gap-2 border-b border-w-line px-4 py-3">
            <Sparkles className="h-3.5 w-3.5 text-w-accent" />
            <h2 className="text-sm font-semibold text-w-text">Review AI ticket</h2>
            <button onClick={onClose} className="ml-auto text-w-dim hover:text-w-text">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="max-h-[70vh] space-y-3 overflow-y-auto px-4 py-3">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Title"
              className="w-full rounded-lg border border-w-line bg-w-surface px-2.5 py-1.5 text-sm text-w-text outline-none focus:border-w-line"
            />
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={7}
              placeholder="Description"
              className="w-full resize-y rounded-lg border border-w-line bg-w-surface px-3 py-2 text-xs text-w-text outline-none focus:border-w-line"
            />

            <div className="grid grid-cols-2 gap-2">
              <label className="block">
                <span className="mb-1 block text-[11px] text-w-dim">Priority</span>
                <select
                  value={priority}
                  onChange={(e) => setPriority(e.target.value as TaskPriority)}
                  className="w-full rounded-lg border border-w-line bg-w-surface px-2 py-1 text-xs capitalize text-w-text outline-none focus:border-w-line"
                >
                  {PRIORITIES.map((p) => (
                    <option key={p} value={p} className="capitalize">
                      {p}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-[11px] text-w-dim">Type</span>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full rounded-lg border border-w-line bg-w-surface px-2 py-1 text-xs capitalize text-w-text outline-none focus:border-w-line"
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c} className="capitalize">
                      {c}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="block">
              <span className="mb-1 block text-[11px] text-w-dim">Column</span>
              <select
                value={boardColumn}
                onChange={(e) => setBoardColumn(e.target.value as BoardColumn)}
                className="w-full rounded-lg border border-w-line bg-w-surface px-2 py-1 text-xs text-w-text outline-none focus:border-w-line"
              >
                {KANBAN_COLUMNS.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>

            {collaborators.length > 0 && (
              <label className="block">
                <span className="mb-1 block text-[11px] text-w-dim">Assignee</span>
                <select
                  value={assignedTo}
                  onChange={(e) => setAssignedTo(e.target.value)}
                  className="w-full rounded-lg border border-w-line bg-w-surface px-2 py-1 text-xs text-w-text outline-none focus:border-w-line"
                >
                  <option value="">Unassigned</option>
                  {collaborators.map((c) => (
                    <option key={c.user_id} value={c.user_id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <div className="rounded-lg bg-w-surface/60 p-2.5">
              <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-w-dim">
                <ListChecks className="h-3 w-3" />
                Checklist
                {steps.length > 0 && <span className="text-w-faint">({steps.length})</span>}
              </div>
              <div className="space-y-1">
                {steps.map((s, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      value={s}
                      onChange={(e) => setSteps((prev) => prev.map((v, idx) => (idx === i ? e.target.value : v)))}
                      className="flex-1 rounded border border-w-line bg-w-surface px-2 py-1 text-xs text-w-text outline-none focus:border-w-line"
                    />
                    <button
                      onClick={() => setSteps((prev) => prev.filter((_, idx) => idx !== i))}
                      className="shrink-0 text-w-faint hover:text-red-400"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
                <div className="flex items-center gap-2">
                  <input
                    value={newStep}
                    onChange={(e) => setNewStep(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        addStep()
                      }
                    }}
                    placeholder="Add a step…"
                    className="flex-1 rounded border border-w-line bg-w-surface px-2 py-1 text-xs text-w-text placeholder-w-faint outline-none focus:border-w-line"
                  />
                  <button onClick={addStep} disabled={!newStep.trim()} className="shrink-0 text-w-dim hover:text-w-text disabled:opacity-40">
                    <Plus className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-w-line px-4 py-3">
            <button onClick={onClose} className="text-xs text-w-dim hover:text-w-text">
              Cancel
            </button>
            <button
              onClick={handleCreate}
              disabled={busy || !title.trim()}
              className="flex items-center gap-1.5 rounded-lg bg-w-accent px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-w-accent-hi disabled:opacity-50"
            >
              {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Create
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
