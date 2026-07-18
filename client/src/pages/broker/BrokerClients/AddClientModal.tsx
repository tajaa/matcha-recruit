import { Plus, X } from 'lucide-react'
import { Button, Input, Modal } from '../../../components/ui'
import type { SetupForm, LocationEntry } from './types'
import { US_STATES, LOCATION_TYPES } from './constants'

type Props = {
  open: boolean
  form: SetupForm
  setForm: (form: SetupForm) => void
  saving: boolean
  addError: string
  onClose: () => void
  onSubmit: (e: React.FormEvent) => void
  addLocation: () => void
  removeLocation: (idx: number) => void
  updateLocation: (idx: number, field: keyof LocationEntry, value: string) => void
}

export function AddClientModal({
  open, form, setForm, saving, addError, onClose, onSubmit,
  addLocation, removeLocation, updateLocation,
}: Props) {
  return (
    <Modal open={open} onClose={onClose} title="Add Client" width="lg">
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Company Info</p>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Company Name"
              value={form.company_name}
              onChange={(e) => setForm({ ...form, company_name: e.target.value })}
              required
            />
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">Industry</label>
              <select
                value={form.industry}
                onChange={(e) => setForm({ ...form, industry: e.target.value })}
                className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
              >
                <option value="">Select industry...</option>
                <option value="healthcare">Healthcare</option>
                <option value="manufacturing">Manufacturing</option>
                <option value="technology">Technology</option>
                <option value="retail">Retail</option>
                <option value="hospitality">Hospitality</option>
                <option value="construction">Construction</option>
                <option value="finance">Finance</option>
                <option value="education">Education</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1">Company Size</label>
              <select
                value={form.company_size}
                onChange={(e) => setForm({ ...form, company_size: e.target.value })}
                className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
              >
                <option value="">Select size...</option>
                <option value="1-10">1-10</option>
                <option value="11-50">11-50</option>
                <option value="51-200">51-200</option>
                <option value="201-500">201-500</option>
                <option value="501-1000">501-1000</option>
                <option value="1001+">1001+</option>
              </select>
            </div>
            <Input
              label="Headcount"
              type="number"
              value={form.headcount}
              onChange={(e) => setForm({ ...form, headcount: e.target.value })}
            />
          </div>
        </div>

        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Primary Contact</p>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Contact Name"
              value={form.contact_name}
              onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
            />
            <Input
              label="Contact Email"
              type="email"
              value={form.contact_email}
              onChange={(e) => setForm({ ...form, contact_email: e.target.value })}
            />
            <Input
              label="Phone (optional)"
              value={form.contact_phone}
              onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
            />
          </div>
        </div>

        {/* Locations */}
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Locations</p>
          {form.locations.length > 0 && (
            <div className="space-y-2 mb-2">
              {form.locations.map((loc, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <Input
                    label=""
                    placeholder="City"
                    value={loc.city}
                    onChange={(e) => updateLocation(idx, 'city', e.target.value)}
                    className="flex-1"
                  />
                  <select
                    value={loc.state}
                    onChange={(e) => updateLocation(idx, 'state', e.target.value)}
                    className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                  >
                    <option value="">State...</option>
                    {US_STATES.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                  <select
                    value={loc.type}
                    onChange={(e) => updateLocation(idx, 'type', e.target.value)}
                    className="bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500"
                  >
                    {LOCATION_TYPES.map((t) => (
                      <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => removeLocation(idx)}
                    className="p-1 text-zinc-500 hover:text-red-400 transition-colors"
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
          <button
            type="button"
            onClick={addLocation}
            className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-1"
          >
            <Plus size={12} />
            Add Location
          </button>
        </div>

        {/* Specialties */}
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Specialties</p>
          <Input
            label=""
            placeholder="e.g., Oncology, Cardiology, Primary Care, Behavioral Health"
            value={form.specialties ?? ''}
            onChange={(e) => setForm({ ...form, specialties: e.target.value })}
          />
          <p className="text-[10px] text-zinc-600 mt-1">Comma-separated if multiple</p>
        </div>

        {/* Notes */}
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium mb-2">Notes</p>
          <textarea
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            placeholder="Additional context about this client, special requirements, timeline notes..."
            rows={3}
            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm px-3 py-2 focus:border-zinc-500 resize-none placeholder:text-zinc-600"
          />
        </div>

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="invite-immediately"
            checked={form.invite_immediately}
            onChange={(e) => setForm({ ...form, invite_immediately: e.target.checked })}
            className="rounded border-zinc-600 bg-zinc-800 text-zinc-600 focus:ring-zinc-500"
          />
          <label htmlFor="invite-immediately" className="text-sm text-zinc-400">
            Send invitation email immediately
          </label>
        </div>

        {addError && <p className="text-sm text-red-400">{addError}</p>}

        <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
          <Button type="submit" size="sm" disabled={saving || !form.company_name.trim()}>
            {saving ? 'Creating...' : 'Create Client Setup'}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  )
}
