import { useState } from 'react'
import { X } from 'lucide-react'

interface Props {
  onSubmit: (body: { title: string; description?: string; due_date?: string; priority?: string }) => Promise<void>
  onCancel: () => void
}

export default function TaskCreateForm({ onSubmit, onCancel }: Props) {
  const [title, setTitle] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [priority, setPriority] = useState('medium')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim()) return
    setSubmitting(true)
    try {
      await onSubmit({
        title: title.trim(),
        due_date: dueDate || undefined,
        priority,
      })
      setTitle('')
      setDueDate('')
      setPriority('medium')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="border border-w-line rounded-lg p-4 bg-w-surface/50 space-y-3"
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-w-text">New Task</span>
        <button type="button" onClick={onCancel} className="text-w-dim hover:text-w-text">
          <X size={14} />
        </button>
      </div>

      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Task title..."
        autoFocus
        className="w-full px-3 py-2 bg-w-surface2 border border-w-line rounded-md text-sm text-w-text placeholder-w-faint outline-none focus:border-w-line"
      />

      <div className="flex items-center gap-3">
        <input
          type="date"
          value={dueDate}
          onChange={(e) => setDueDate(e.target.value)}
          className="px-3 py-1.5 bg-w-surface2 border border-w-line rounded-md text-xs text-w-text outline-none focus:border-w-line"
        />

        <select
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
          className="px-3 py-1.5 bg-w-surface2 border border-w-line rounded-md text-xs text-w-text outline-none focus:border-w-line"
        >
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="critical">Critical</option>
        </select>

        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 text-xs text-w-dim hover:text-w-text transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!title.trim() || submitting}
            className="px-4 py-1.5 text-xs font-medium bg-w-accent hover:bg-w-accent-hi text-white rounded-md transition-colors disabled:opacity-50"
          >
            {submitting ? 'Adding...' : 'Add Task'}
          </button>
        </div>
      </div>
    </form>
  )
}
