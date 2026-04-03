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
      className="border border-zinc-700 rounded-lg p-4 bg-zinc-900/50 space-y-3"
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-zinc-200">New Task</span>
        <button type="button" onClick={onCancel} className="text-zinc-500 hover:text-zinc-300">
          <X size={14} />
        </button>
      </div>

      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Task title..."
        autoFocus
        className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-md text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-zinc-500"
      />

      <div className="flex items-center gap-3">
        <input
          type="date"
          value={dueDate}
          onChange={(e) => setDueDate(e.target.value)}
          className="px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-md text-xs text-zinc-300 outline-none focus:border-zinc-500"
        />

        <select
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
          className="px-3 py-1.5 bg-zinc-800 border border-zinc-700 rounded-md text-xs text-zinc-300 outline-none focus:border-zinc-500"
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
            className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!title.trim() || submitting}
            className="px-4 py-1.5 text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded-md transition-colors disabled:opacity-50"
          >
            {submitting ? 'Adding...' : 'Add Task'}
          </button>
        </div>
      </div>
    </form>
  )
}
