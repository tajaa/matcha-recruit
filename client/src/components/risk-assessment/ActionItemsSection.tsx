import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, Button, Input, Modal, Select, Textarea } from '../ui'
import { fmt, capitalize } from '../../types/risk-assessment'
import type { ActionItem, AssignableUser } from '../../types/risk-assessment'

const SOURCE_TYPE_OPTIONS = [
  { value: 'wage_violation', label: 'Wage Violation' },
  { value: 'er_case', label: 'ER Case' },
]

const EMPTY_ITEM_FORM = {
  title: '',
  description: '',
  source_type: 'wage_violation',
  assigned_to: '',
  due_date: '',
}

type Props = {
  qs: string
}

export function ActionItemsSection({ qs }: Props) {
  const [actionItems, setActionItems] = useState<ActionItem[]>([])
  const [loadingItems, setLoadingItems] = useState(false)
  const [statusFilter, setStatusFilter] = useState<'open' | 'all'>('open')
  const [showCreateItem, setShowCreateItem] = useState(false)
  const [itemForm, setItemForm] = useState(EMPTY_ITEM_FORM)
  const [assignableUsers, setAssignableUsers] = useState<AssignableUser[]>([])
  const [savingItem, setSavingItem] = useState(false)

  useEffect(() => {
    setLoadingItems(true)
    const sep = qs ? '&' : '?'
    api.get<ActionItem[]>(`/risk-assessment/action-items${qs}${sep}status=${statusFilter}`)
      .then(setActionItems)
      .catch(() => setActionItems([]))
      .finally(() => setLoadingItems(false))
  }, [statusFilter, qs])

  useEffect(() => {
    if (!showCreateItem) return
    api.get<AssignableUser[]>(`/risk-assessment/assignable-users${qs}`)
      .then(setAssignableUsers)
      .catch(() => setAssignableUsers([]))
  }, [showCreateItem, qs])

  async function handleCreateItem(e: React.FormEvent) {
    e.preventDefault()
    setSavingItem(true)
    try {
      const body: Record<string, unknown> = {
        title: itemForm.title,
        source_type: itemForm.source_type,
      }
      if (itemForm.description) body.description = itemForm.description
      if (itemForm.assigned_to) body.assigned_to = itemForm.assigned_to
      if (itemForm.due_date) body.due_date = itemForm.due_date

      const created = await api.post<ActionItem>('/risk-assessment/action-items', body)
      setActionItems((prev) => [created, ...prev])
      setShowCreateItem(false)
      setItemForm(EMPTY_ITEM_FORM)
    } finally {
      setSavingItem(false)
    }
  }

  async function handleComplete(id: string) {
    const updated = await api.put<ActionItem>(`/risk-assessment/action-items/${id}`, { status: 'completed' })
    setActionItems((prev) => prev.map((item) => (item.id === id ? updated : item)))
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
          Action Items
        </h2>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {(['open', 'all'] as const).map((f) => (
              <Button
                key={f}
                variant={statusFilter === f ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setStatusFilter(f)}
              >
                {capitalize(f)}
              </Button>
            ))}
          </div>
          <Button size="sm" onClick={() => setShowCreateItem(true)}>
            Add Item
          </Button>
        </div>
      </div>

      {loadingItems ? (
        <p className="text-sm text-zinc-500">Loading...</p>
      ) : actionItems.length === 0 ? (
        <p className="text-sm text-zinc-500">No action items.</p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-800">
          <table className="w-full text-sm text-left">
            <thead className="bg-zinc-900/50 text-zinc-400">
              <tr>
                <th className="px-4 py-3 font-medium">Title</th>
                <th className="px-4 py-3 font-medium">Source</th>
                <th className="px-4 py-3 font-medium">Assigned To</th>
                <th className="px-4 py-3 font-medium">Due</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {actionItems.map((item) => (
                <tr key={item.id} className="text-zinc-300">
                  <td className="px-4 py-3">
                    <p className="text-zinc-100">{item.title}</p>
                    {item.description && (
                      <p className="text-xs text-zinc-500 mt-0.5 line-clamp-1">{item.description}</p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-400">
                    {item.source_type.replace(/_/g, ' ')}
                    {item.source_ref && (
                      <span className="ml-1 text-zinc-600">#{item.source_ref}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-400">
                    {item.assigned_to_name ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-400">
                    {fmt(item.due_date)}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={item.status === 'completed' ? 'success' : 'neutral'}>
                      {capitalize(item.status)}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    {item.status !== 'completed' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleComplete(item.id)}
                      >
                        Complete
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={showCreateItem} onClose={() => setShowCreateItem(false)} title="Add Action Item">
        <form onSubmit={handleCreateItem} className="space-y-4">
          <Input
            label="Title"
            required
            value={itemForm.title}
            onChange={(e) => setItemForm({ ...itemForm, title: e.target.value })}
            placeholder="What needs to be done?"
          />
          <Textarea
            label="Description"
            value={itemForm.description}
            onChange={(e) => setItemForm({ ...itemForm, description: e.target.value })}
            placeholder="Optional details"
          />
          <Select
            label="Source Type"
            options={SOURCE_TYPE_OPTIONS}
            value={itemForm.source_type}
            onChange={(e) => setItemForm({ ...itemForm, source_type: e.target.value })}
          />
          {assignableUsers.length > 0 && (
            <Select
              label="Assign To"
              options={[{ value: '', label: 'Unassigned' }, ...assignableUsers.map((u) => ({ value: u.id, label: u.name }))]}
              value={itemForm.assigned_to}
              onChange={(e) => setItemForm({ ...itemForm, assigned_to: e.target.value })}
            />
          )}
          <Input
            label="Due Date"
            type="date"
            value={itemForm.due_date}
            onChange={(e) => setItemForm({ ...itemForm, due_date: e.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" type="button" onClick={() => setShowCreateItem(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={savingItem}>
              {savingItem ? 'Saving...' : 'Create'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
