import { Button, Input, Modal } from '../../../components/ui'
import type { CreateForm } from './types'

type AddBrokerModalProps = {
  open: boolean
  form: CreateForm
  setForm: (form: CreateForm) => void
  saving: boolean
  addError: string
  onClose: () => void
  onSubmit: (e: React.FormEvent) => void
}

export function AddBrokerModal({ open, form, setForm, saving, addError, onClose, onSubmit }: AddBrokerModalProps) {
  return (
    <Modal open={open} onClose={onClose} title="Add Broker" width="lg">
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Broker Info</p>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Broker Name"
              value={form.broker_name}
              onChange={(e) => setForm({ ...form, broker_name: e.target.value })}
              required
            />
            <Input
              label="Slug (optional)"
              placeholder="auto-generated"
              value={form.slug}
              onChange={(e) => setForm({ ...form, slug: e.target.value })}
            />
          </div>
        </div>

        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Owner Account</p>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Full Name"
              value={form.owner_name}
              onChange={(e) => setForm({ ...form, owner_name: e.target.value })}
              required
            />
            <Input
              label="Email"
              type="email"
              value={form.owner_email}
              onChange={(e) => setForm({ ...form, owner_email: e.target.value })}
              required
            />
            <Input
              label="Password (optional)"
              type="password"
              placeholder="auto-generated if blank"
              value={form.owner_password}
              onChange={(e) => setForm({ ...form, owner_password: e.target.value })}
            />
          </div>
        </div>

        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Configuration</p>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">Support Routing</label>
              <select
                value={form.support_routing}
                onChange={(e) => setForm({ ...form, support_routing: e.target.value })}
                className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
              >
                <option value="shared">Shared</option>
                <option value="broker_first">Broker First</option>
                <option value="matcha_first">Matcha First</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">Billing Mode</label>
              <select
                value={form.billing_mode}
                onChange={(e) => setForm({ ...form, billing_mode: e.target.value })}
                className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
              >
                <option value="direct">Direct</option>
                <option value="reseller">Reseller</option>
                <option value="hybrid">Hybrid</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">Invoice Owner</label>
              <select
                value={form.invoice_owner}
                onChange={(e) => setForm({ ...form, invoice_owner: e.target.value })}
                className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
              >
                <option value="matcha">Matcha</option>
                <option value="broker">Broker</option>
              </select>
            </div>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-zinc-300 mb-1">Allocated Seats</label>
          <input
            type="number"
            min={0}
            value={form.allocated_seats}
            onChange={(e) => setForm({ ...form, allocated_seats: e.target.value })}
            placeholder="0"
            className="w-40 bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
          />
          <p className="mt-1 text-xs text-zinc-500">Seat pool the brokerage can apportion to its clients.</p>
        </div>

        {addError && <p className="text-sm text-red-400">{addError}</p>}

        <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
          <Button
            type="submit"
            size="sm"
            disabled={saving || !form.broker_name.trim() || !form.owner_email.trim() || !form.owner_name.trim()}
          >
            {saving ? 'Creating...' : 'Create Broker'}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  )
}
