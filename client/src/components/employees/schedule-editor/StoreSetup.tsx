import { AlertTriangle, Pencil, Plus, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { StoreSetup } from '../../../hooks/employees/useStoreSetup'
import type { CompanyLocation } from '../../../hooks/useLocationScope'
import type { ScheduleStore } from '../../../types/employeeSchedule'
import { useToast } from '../../ui'
import AssignEmployeesToStoreModal from './AssignEmployeesToStoreModal'
import StoreFormModal from './StoreFormModal'

const actionCls = 'inline-flex items-center gap-1 rounded-lg border border-zinc-700 px-2 py-1.5 text-xs text-zinc-300 hover:border-zinc-500 hover:text-zinc-100'

/** "+ Add store" / "Edit store", beside a location picker. */
/** `compact` draws icon-only buttons (names kept for screen readers and the
 *  tooltip) for a toolbar where the labels crowd out the week controls. */
export function StoreActions({ setup, canEdit, compact = false }: { setup: StoreSetup; canEdit: boolean; compact?: boolean }) {
  const cls = compact ? 'rounded-lg border border-zinc-800 p-1.5 text-zinc-400 hover:text-zinc-100' : actionCls
  return (
    <div className="inline-flex items-center gap-1.5">
      {canEdit && (
        <button type="button" className={cls} onClick={() => setup.setModal('edit')} aria-label="Edit store details" title="Edit store details">
          <Pencil className="h-3.5 w-3.5" />{!compact && ' Edit store'}
        </button>
      )}
      <button type="button" className={cls} onClick={() => setup.setModal('add')} aria-label="Add store" title="Add store">
        <Plus className="h-3.5 w-3.5" />{!compact && ' Add store'}
      </button>
    </div>
  )
}

interface StoreSetupNoticeProps {
  setup: StoreSetup
  store: CompanyLocation | null
  className?: string
}

/** What still stands between this store and a published week, with the fix
 *  one click away. Renders nothing once the store is ready and staffed. */
export function StoreSetupNotice({ setup, store, className = '' }: StoreSetupNoticeProps) {
  const notReady = store && setup.readiness && !setup.readiness.ready_to_publish
  const waiting = setup.unassigned.length
  if (!notReady && !(store && waiting)) return null
  return (
    <div className={`space-y-2 ${className}`}>
      {notReady && (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-500/25 bg-amber-500/[0.06] px-3 py-2 text-xs text-amber-100">
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-300" />
          <span>{setup.readiness?.message ?? "This store isn't ready to publish yet."}</span>
          <button type="button" onClick={() => setup.setModal('edit')} className="ml-auto rounded-lg border border-amber-400/40 px-2.5 py-1 font-medium text-amber-100 hover:bg-amber-400/10">
            Fix store details
          </button>
        </div>
      )}
      {store && waiting > 0 && (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-zinc-300">
          <Users className="h-4 w-4 shrink-0 text-zinc-400" />
          <span>
            {waiting} {waiting === 1 ? "employee isn't" : "employees aren't"} assigned to a store, so they don't show up on any schedule.
          </span>
          <button type="button" onClick={() => setup.setModal('assign')} className="ml-auto rounded-lg border border-zinc-600 px-2.5 py-1 font-medium text-zinc-100 hover:bg-white/[0.06]">
            Assign to {store.name || 'this store'}
          </button>
        </div>
      )}
    </div>
  )
}

interface StoreSetupModalsProps {
  setup: StoreSetup
  store: CompanyLocation | null
  /** A store was added or edited: re-read the list and (for a new one) select it. */
  onStoreSaved(store: ScheduleStore, created: boolean): void | Promise<void>
  /** Employees were placed at the store: the roster needs re-reading. */
  onRosterChanged(): void
}

export function StoreSetupModals({ setup, store, onStoreSaved, onRosterChanged }: StoreSetupModalsProps) {
  const { toast } = useToast()
  const editing = setup.modal === 'edit' ? store : null
  return (
    <>
      <StoreFormModal
        open={setup.modal === 'add' || (setup.modal === 'edit' && !!store)}
        store={editing}
        notice={editing && setup.readiness && !setup.readiness.ready_to_publish ? setup.readiness.message : null}
        onClose={() => setup.setModal(null)}
        onSaved={async (saved) => {
          const created = setup.modal === 'add'
          setup.setModal(null)
          await onStoreSaved(saved, created)
          setup.refresh()
          toast(created ? `${saved.name ?? 'Store'} added` : 'Store details saved', 'success')
        }}
      />
      {store && (
        <AssignEmployeesToStoreModal
          open={setup.modal === 'assign'}
          storeId={store.id}
          storeName={store.name || 'this store'}
          employees={setup.unassigned}
          onClose={() => setup.setModal(null)}
          onAssigned={(count) => {
            setup.setModal(null)
            setup.refresh()
            onRosterChanged()
            toast(`${count} ${count === 1 ? 'employee' : 'employees'} assigned`, 'success')
          }}
          onPartiallyAssigned={() => {
            setup.refresh()
            onRosterChanged()
          }}
        />
      )}
    </>
  )
}

/** The first thing a brand-new account sees on a schedule screen. */
export function NoStoresYet({ setup }: { setup: StoreSetup }) {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-center">
      <p className="text-sm text-zinc-300">Add your first store to start scheduling.</p>
      <p className="max-w-sm text-xs text-zinc-500">Each store gets its own schedule. You can add more at any time.</p>
      <button type="button" onClick={() => setup.setModal('add')} className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-100 px-3 py-2 text-sm font-medium text-zinc-900 hover:bg-white">
        <Plus className="h-4 w-4" /> Add a store
      </button>
    </div>
  )
}

/** Shown where a roster would be when the store has nobody on it. */
export function EmptyRosterHelp({ setup, storeName }: { setup: StoreSetup; storeName: string }) {
  const waiting = setup.unassigned.length
  return (
    <div className="space-y-2 px-2 py-3 text-xs text-zinc-500">
      <p>No one is assigned to {storeName} yet.</p>
      {waiting > 0 ? (
        <button type="button" onClick={() => setup.setModal('assign')} className="text-emerald-300 hover:text-emerald-200">
          Assign {waiting} waiting {waiting === 1 ? 'employee' : 'employees'}
        </button>
      ) : (
        <Link to="/app/employees" className="text-emerald-300 hover:text-emerald-200">Import your roster</Link>
      )}
    </div>
  )
}
