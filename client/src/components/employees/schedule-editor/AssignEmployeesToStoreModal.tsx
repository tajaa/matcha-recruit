import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { assignEmployeesToStore } from '../../../api/employees/scheduleStores'
import { errorMessage, type UnassignedEmployee } from '../../../types/employeeSchedule'
import { Button, Modal } from '../../ui'

interface AssignEmployeesToStoreModalProps {
  open: boolean
  storeId: string
  storeName: string
  /** Active employees with no store. Only they can be placed from here. */
  employees: UnassignedEmployee[]
  onClose(): void
  onAssigned(count: number): void
}

function displayName(employee: UnassignedEmployee): string {
  return [employee.first_name, employee.last_name].filter(Boolean).join(' ') || employee.email || 'Unnamed employee'
}

/** Place the people an import left without a store. The schedule roster only
 *  lists employees who have one, so this is what makes them schedulable. */
export default function AssignEmployeesToStoreModal({
  open, storeName, onClose, ...body
}: AssignEmployeesToStoreModalProps) {
  const [saving, setSaving] = useState(false)
  return (
    <Modal open={open} onClose={onClose} title={`Assign employees to ${storeName}`} dismissible={!saving}>
      {/* The Modal renders nothing while closed, so the body mounts fresh on
          every open, with everyone ticked. */}
      <AssignBody {...body} storeName={storeName} onClose={onClose} saving={saving} setSaving={setSaving} />
    </Modal>
  )
}

interface AssignBodyProps extends Omit<AssignEmployeesToStoreModalProps, 'open'> {
  saving: boolean
  setSaving(saving: boolean): void
}

function AssignBody({ storeId, storeName, employees, onClose, onAssigned, saving, setSaving }: AssignBodyProps) {
  // Everyone starts ticked: the common case is a one-store shop placing its
  // whole imported roster.
  const [selected, setSelected] = useState<Set<string>>(() => new Set(employees.map((employee) => employee.id)))
  const [error, setError] = useState<string | null>(null)

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function assign() {
    setSaving(true)
    setError(null)
    try {
      const result = await assignEmployeesToStore(storeId, [...selected])
      onAssigned(result.assigned.length)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setSaving(false)
    }
  }

  const allSelected = employees.length > 0 && selected.size === employees.length

  return (
    <div className="space-y-4">
      <p className="text-sm text-zinc-400">
        These employees have no store yet, so they don't appear on any schedule. Pick who works at {storeName}.
      </p>
      {employees.length === 0 ? (
        <p className="text-sm text-zinc-500">Everyone already has a store.</p>
      ) : (
        <>
          <label className="flex items-center gap-2 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={() => setSelected(allSelected ? new Set() : new Set(employees.map((employee) => employee.id)))}
            />
            Select all ({employees.length})
          </label>
          <ul className="max-h-72 space-y-1 overflow-y-auto rounded-lg border border-white/[0.08] p-2">
            {employees.map((employee) => (
              <li key={employee.id}>
                <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm text-zinc-200 hover:bg-white/[0.04]">
                  <input type="checkbox" checked={selected.has(employee.id)} onChange={() => toggle(employee.id)} />
                  <span className="min-w-0 flex-1 truncate">{displayName(employee)}</span>
                  {employee.job_title && <span className="shrink-0 text-xs text-zinc-500">{employee.job_title}</span>}
                </label>
              </li>
            ))}
          </ul>
        </>
      )}
      {error && <p role="alert" className="rounded border border-red-900/40 bg-red-950/30 px-3 py-2 text-sm text-red-300">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" disabled={saving} onClick={onClose}>Cancel</Button>
        <Button disabled={saving || selected.size === 0} onClick={() => void assign()}>
          {saving && <Loader2 className="h-4 w-4 animate-spin" />}
          Assign {selected.size || ''} to {storeName}
        </Button>
      </div>
    </div>
  )
}
