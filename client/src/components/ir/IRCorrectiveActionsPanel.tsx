import { useState } from 'react'
import { Loader2, Plus, Trash2, AlertTriangle } from 'lucide-react'
import { Badge, Button, Select } from '../ui'
import { useCorrectiveActions } from '../../hooks/ir/useCorrectiveActions'
import type {
  CorrectiveAction,
  CorrectiveActionPriority,
  CorrectiveActionStatus,
  CorrectiveActionEffectiveness,
} from '../../types/ir'

const STATUS_OPTIONS: { value: CorrectiveActionStatus; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'completed', label: 'Completed' },
  { value: 'verified', label: 'Verified' },
  { value: 'cancelled', label: 'Cancelled' },
]

const PRIORITY_OPTIONS: { value: CorrectiveActionPriority; label: string }[] = [
  { value: 'immediate', label: 'Immediate' },
  { value: 'short_term', label: 'Short-term' },
  { value: 'long_term', label: 'Long-term' },
]

const EFFECTIVENESS_OPTIONS: { value: CorrectiveActionEffectiveness | ''; label: string }[] = [
  { value: '', label: '— Not verified —' },
  { value: 'pending', label: 'Pending review' },
  { value: 'effective', label: 'Effective' },
  { value: 'ineffective', label: 'Ineffective' },
]

const STATUS_BADGE: Record<CorrectiveActionStatus, string> = {
  open: 'bg-zinc-800 text-zinc-300',
  in_progress: 'bg-blue-500/15 text-blue-300',
  completed: 'bg-emerald-500/15 text-emerald-300',
  verified: 'bg-emerald-500/25 text-emerald-200',
  cancelled: 'bg-zinc-800 text-zinc-500 line-through',
}

const PRIORITY_LABEL: Record<CorrectiveActionPriority, string> = {
  immediate: 'Immediate',
  short_term: 'Short-term',
  long_term: 'Long-term',
}

export function IRCorrectiveActionsPanel({ incidentId }: { incidentId: string }) {
  const { actions, loading, error, refetch, createAction, updateAction, deleteAction } =
    useCorrectiveActions(incidentId)

  const [showAdd, setShowAdd] = useState(false)
  const [desc, setDesc] = useState('')
  const [owner, setOwner] = useState('')
  const [due, setDue] = useState('')
  const [priority, setPriority] = useState<CorrectiveActionPriority>('short_term')
  const [saving, setSaving] = useState(false)
  const [mutError, setMutError] = useState('')

  const openCount = actions.filter((a) => a.status === 'open' || a.status === 'in_progress').length
  const overdueCount = actions.filter((a) => a.overdue).length

  async function submitNew() {
    if (!desc.trim()) return
    setSaving(true)
    setMutError('')
    try {
      await createAction({
        description: desc.trim(),
        priority,
        assignee_name: owner.trim() || null,
        due_date: due || null,
      })
      setDesc(''); setOwner(''); setDue(''); setPriority('short_term'); setShowAdd(false)
    } catch (e) {
      setMutError(e instanceof Error ? e.message : 'Failed to add action')
    } finally {
      setSaving(false)
    }
  }

  async function patch(id: string, p: Partial<CorrectiveAction>) {
    setMutError('')
    try {
      await updateAction(id, p)
    } catch (e) {
      setMutError(e instanceof Error ? e.message : 'Failed to update action')
    }
  }

  async function remove(id: string) {
    setMutError('')
    try {
      await deleteAction(id)
    } catch (e) {
      setMutError(e instanceof Error ? e.message : 'Failed to delete action')
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
          Corrective Actions
          {openCount > 0 && (
            <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full bg-zinc-800 text-zinc-300 normal-case">
              {openCount} open
            </span>
          )}
          {overdueCount > 0 && (
            <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded-full bg-red-500/15 text-red-300 normal-case">
              {overdueCount} overdue
            </span>
          )}
        </h3>
        {!showAdd && (
          <Button size="sm" variant="secondary" onClick={() => setShowAdd(true)}>
            <Plus className="w-3.5 h-3.5 mr-1" /> Add
          </Button>
        )}
      </div>

      {(error || mutError) && (
        <div className="mb-2 flex items-center justify-between gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          <span>{mutError || error}</span>
          {error && !mutError && (
            <button className="underline shrink-0" onClick={() => refetch()}>Retry</button>
          )}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-zinc-500 py-3">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
        </div>
      ) : (
        <div className="space-y-2">
          {actions.length === 0 && !showAdd && (
            <p className="text-xs text-zinc-600 py-1">
              No corrective actions yet. Add one to assign an owner and track it to completion.
            </p>
          )}

          {actions.map((a) => (
            <div key={a.id} className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm text-zinc-200 break-words">{a.description}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-500">
                    <span className={`px-1.5 py-0.5 rounded-full ${STATUS_BADGE[a.status]}`}>
                      {STATUS_OPTIONS.find((s) => s.value === a.status)?.label}
                    </span>
                    <span>· {PRIORITY_LABEL[a.priority]}</span>
                    {(a.assigned_to_name || a.assignee_name) && (
                      <span>· {a.assigned_to_name || a.assignee_name}</span>
                    )}
                    {a.due_date && (
                      <span className={a.overdue ? 'text-red-400 font-medium' : ''}>
                        {a.overdue && <AlertTriangle className="inline w-3 h-3 mr-0.5 -mt-0.5" />}
                        due {a.due_date}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  className="text-zinc-600 hover:text-red-400 shrink-0"
                  title="Delete"
                  onClick={() => remove(a.id)}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>

              <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
                <div>
                  <label className="block text-[10px] uppercase tracking-wide text-zinc-600 mb-1">Status</label>
                  <Select
                    label=""
                    options={STATUS_OPTIONS}
                    value={a.status}
                    onChange={(e) => patch(a.id, { status: e.target.value as CorrectiveActionStatus })}
                  />
                </div>
                {(a.status === 'completed' || a.status === 'verified') && (
                  <div>
                    <label className="block text-[10px] uppercase tracking-wide text-zinc-600 mb-1">
                      Effectiveness
                    </label>
                    <Select
                      label=""
                      options={EFFECTIVENESS_OPTIONS}
                      value={a.effectiveness || ''}
                      onChange={(e) =>
                        patch(a.id, {
                          effectiveness: (e.target.value || null) as CorrectiveActionEffectiveness | null,
                        })
                      }
                    />
                  </div>
                )}
              </div>

              {a.status === 'verified' && a.effectiveness && (
                <div className="mt-2">
                  <Badge variant={a.effectiveness === 'effective' ? 'success' : a.effectiveness === 'ineffective' ? 'danger' : 'neutral'}>
                    Verified: {a.effectiveness}
                  </Badge>
                </div>
              )}
            </div>
          ))}

          {showAdd && (
            <div className="rounded-lg border border-zinc-700 bg-zinc-900/60 p-3 space-y-2">
              <textarea
                className="w-full bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-200 px-3 py-2 min-h-[60px] focus:outline-none focus:border-zinc-600"
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                placeholder="Describe the corrective/preventive action…"
              />
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <div>
                  <label className="block text-[10px] uppercase tracking-wide text-zinc-600 mb-1">Owner</label>
                  <input
                    className="w-full bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-200 px-3 py-2 focus:outline-none focus:border-zinc-600"
                    value={owner}
                    onChange={(e) => setOwner(e.target.value)}
                    placeholder="Name"
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wide text-zinc-600 mb-1">Due date</label>
                  <input
                    type="date"
                    className="w-full bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-zinc-200 px-3 py-2 focus:outline-none focus:border-zinc-600"
                    value={due}
                    onChange={(e) => setDue(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase tracking-wide text-zinc-600 mb-1">Priority</label>
                  <Select
                    label=""
                    options={PRIORITY_OPTIONS}
                    value={priority}
                    onChange={(e) => setPriority(e.target.value as CorrectiveActionPriority)}
                  />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" disabled={saving || !desc.trim()} onClick={submitNew}>
                  {saving ? 'Adding…' : 'Add action'}
                </Button>
                <Button size="sm" variant="secondary" disabled={saving} onClick={() => { setShowAdd(false); setMutError('') }}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
