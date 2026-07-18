import { Button, Modal } from '../../../components/ui'
import type { Broker, EditForm } from './types'

type EditBrokerModalProps = {
  editBroker: Broker | null
  editForm: EditForm
  setEditForm: (form: EditForm) => void
  editSaving: boolean
  editError: string
  onClose: () => void
  onSubmit: (e: React.FormEvent) => void
}

export function EditBrokerModal({ editBroker, editForm, setEditForm, editSaving, editError, onClose, onSubmit }: EditBrokerModalProps) {
  return (
    <Modal open={!!editBroker} onClose={onClose} title={`Edit — ${editBroker?.name}`} width="md">
      {editBroker && (
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">Status</label>
              <select
                value={editForm.status}
                onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
                className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
              >
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
                <option value="terminated">Terminated</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">Support Routing</label>
              <select
                value={editForm.support_routing}
                onChange={(e) => setEditForm({ ...editForm, support_routing: e.target.value })}
                className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
              >
                <option value="shared">Shared</option>
                <option value="broker_first">Broker First</option>
                <option value="matcha_first">Matcha First</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-1">Allocated Seats</label>
            <input
              type="number"
              min={0}
              value={editForm.allocated_seats}
              onChange={(e) => setEditForm({ ...editForm, allocated_seats: e.target.value })}
              className="w-40 bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
            />
            {editBroker && (editBroker.seats_used ?? 0) > 0 && (
              <p className="mt-1 text-xs text-zinc-500">{editBroker.seats_used} seats currently apportioned.</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-300 mb-1">Plan</label>
            <select
              value={editForm.plan}
              onChange={(e) => setEditForm({ ...editForm, plan: e.target.value })}
              className="w-40 bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
            >
              <option value="standard">Standard</option>
              <option value="pro">Pro (off-platform clients)</option>
            </select>
            <p className="mt-1 text-xs text-zinc-500">Pro unlocks the off-platform "External Book" (non-tenant clients).</p>
          </div>

          {editForm.status === 'terminated' && (
            <p className="text-xs text-red-400 bg-red-900/20 border border-red-800/30 rounded px-2 py-1.5">
              Terminating a broker will prevent them from logging in and managing clients. Existing client links will remain but no new onboarding will be possible.
            </p>
          )}

          {editError && <p className="text-sm text-red-400">{editError}</p>}

          <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
            <Button type="submit" size="sm" disabled={editSaving}>
              {editSaving ? 'Saving...' : 'Save Changes'}
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </Modal>
  )
}
