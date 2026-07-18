import { useState } from 'react'
import { X, Loader2 } from 'lucide-react'
import type { MWProjectTaskCreate, ProjectCollaborator, BoardColumn, TaskPriority } from '../../types/matcha-work'
import type { KanbanTemplate } from '../../utils/kanbanTemplates'
import { composeDescription } from '../../utils/kanbanTemplates'

const PRIORITIES: TaskPriority[] = ['critical', 'high', 'medium', 'low']

interface TemplateComposeModalProps {
  template: KanbanTemplate
  column: BoardColumn
  collaborators: ProjectCollaborator[]
  busy: boolean
  onCreate: (payload: MWProjectTaskCreate) => void
  onClose: () => void
}

export default function TemplateComposeModal({
  template,
  column,
  collaborators,
  busy,
  onCreate,
  onClose,
}: TemplateComposeModalProps) {
  const [title, setTitle] = useState('')
  const [priority, setPriority] = useState<TaskPriority>(template.defaultPriority)
  const [assignedTo, setAssignedTo] = useState('')
  const [values, setValues] = useState<Record<string, string>>({})

  const Icon = template.icon

  function setField(key: string, v: string) {
    setValues((prev) => ({ ...prev, [key]: v }))
  }

  function handleCreate() {
    const t = title.trim()
    if (!t || busy) return
    onCreate({
      title: t,
      board_column: column,
      priority,
      assigned_to: assignedTo || null,
      description: composeDescription(template.fields, values) || null,
      category: template.key,
    })
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-xl border border-w-line bg-w-bg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-w-line px-4 py-3">
          <Icon className={`h-3.5 w-3.5 ${template.colorClass}`} />
          <h2 className="text-sm font-semibold text-w-text">New {template.displayName} Ticket</h2>
          <button onClick={onClose} className="ml-auto text-w-dim hover:text-w-text">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[70vh] space-y-3 overflow-y-auto px-4 py-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            autoFocus
            placeholder="Title"
            className="w-full rounded-lg border border-w-line bg-w-surface px-2.5 py-1.5 text-sm text-w-text outline-none focus:border-w-line"
          />

          {template.fields.map((field) => (
            <label key={field.key} className="block">
              <span className="mb-1 block text-[11px] text-w-dim">{field.label}</span>
              {typeof field.kind === 'object' ? (
                <select
                  value={values[field.key] ?? ''}
                  onChange={(e) => setField(field.key, e.target.value)}
                  className="w-full rounded-lg border border-w-line bg-w-surface px-2 py-1.5 text-xs text-w-text outline-none focus:border-w-line"
                >
                  <option value="">—</option>
                  {field.kind.picker.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              ) : field.kind === 'multi' ? (
                <textarea
                  value={values[field.key] ?? ''}
                  onChange={(e) => setField(field.key, e.target.value)}
                  rows={3}
                  placeholder={field.placeholder}
                  className="w-full resize-y rounded-lg border border-w-line bg-w-surface px-2.5 py-1.5 text-xs text-w-text placeholder-w-faint outline-none focus:border-w-line"
                />
              ) : (
                <input
                  value={values[field.key] ?? ''}
                  onChange={(e) => setField(field.key, e.target.value)}
                  placeholder={field.placeholder}
                  className="w-full rounded-lg border border-w-line bg-w-surface px-2.5 py-1.5 text-xs text-w-text placeholder-w-faint outline-none focus:border-w-line"
                />
              )}
            </label>
          ))}

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
            Add
          </button>
        </div>
      </div>
    </div>
  )
}
