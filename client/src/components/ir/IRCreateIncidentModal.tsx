import { useState } from 'react'
import { api } from '../../api/client'
import { Button, Input, Modal, Select, Textarea } from '../ui'
import type { IRIncident, IRIncidentType, IRWitness } from '../../types/ir'
import { INCIDENT_TYPE_OPTIONS, SEVERITY_OPTIONS } from '../../types/ir'

const EMPTY_FORM = {
  incident_type: 'safety' as IRIncidentType,
  title: '',
  description: '',
  severity: 'medium',
  location: '',
  date_occurred: '',
  reported_by_name: '',
  reported_by_email: '',
  injured_person: '',
  body_parts: '',
  injury_type: '',
  treatment: '',
  osha_recordable: false,
  policy_violated: '',
  manager_notified: false,
  asset_damaged: '',
  estimated_cost: '',
  insurance_claim: false,
  potential_outcome: '',
  hazard_identified: '',
}

type Props = {
  open: boolean
  onClose: () => void
  onCreated: (incident: IRIncident) => void
}

export function IRCreateIncidentModal({ open, onClose, onCreated }: Props) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [witnesses, setWitnesses] = useState<{ name: string; contact: string }[]>([])
  const [saving, setSaving] = useState(false)

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const categoryData: Record<string, unknown> = {}
      if (form.incident_type === 'safety') {
        if (form.injured_person) categoryData.injured_person = form.injured_person
        if (form.body_parts) categoryData.body_parts = form.body_parts.split(',').map((s) => s.trim()).filter(Boolean)
        if (form.injury_type) categoryData.injury_type = form.injury_type
        if (form.treatment) categoryData.treatment = form.treatment
        categoryData.osha_recordable = form.osha_recordable
      } else if (form.incident_type === 'behavioral') {
        if (form.policy_violated) categoryData.policy_violated = form.policy_violated
        categoryData.manager_notified = form.manager_notified
      } else if (form.incident_type === 'property') {
        if (form.asset_damaged) categoryData.asset_damaged = form.asset_damaged
        if (form.estimated_cost) categoryData.estimated_cost = parseFloat(form.estimated_cost)
        categoryData.insurance_claim = form.insurance_claim
      } else if (form.incident_type === 'near_miss') {
        if (form.potential_outcome) categoryData.potential_outcome = form.potential_outcome
        if (form.hazard_identified) categoryData.hazard_identified = form.hazard_identified
      }

      const witnessPayload: IRWitness[] = witnesses
        .filter((w) => w.name.trim())
        .map((w) => ({ name: w.name.trim(), contact: w.contact.trim() || null }))

      const created = await api.post<IRIncident>('/ir/incidents', {
        incident_type: form.incident_type,
        title: form.title,
        description: form.description || null,
        severity: form.severity,
        location: form.location || null,
        occurred_at: form.date_occurred ? new Date(form.date_occurred).toISOString() : new Date().toISOString(),
        reported_by_name: form.reported_by_name || 'Unknown',
        reported_by_email: form.reported_by_email || null,
        witnesses: witnessPayload,
        category_data: Object.keys(categoryData).length > 0 ? categoryData : null,
      })
      setForm(EMPTY_FORM)
      setWitnesses([])
      onCreated(created)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Report Incident">
      <form onSubmit={handleCreate} className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
        <Select
          label="Incident Type"
          options={INCIDENT_TYPE_OPTIONS}
          value={form.incident_type}
          onChange={(e) => setForm({ ...form, incident_type: e.target.value as IRIncidentType })}
        />
        <Input
          label="Title"
          required
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
          placeholder="Brief description of the incident"
        />
        <Textarea
          label="Description"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          placeholder="What happened? Include relevant details."
        />
        <div className="grid grid-cols-2 gap-3">
          <Select
            label="Severity"
            options={SEVERITY_OPTIONS}
            value={form.severity}
            onChange={(e) => setForm({ ...form, severity: e.target.value })}
          />
          <Input
            label="Location"
            value={form.location}
            onChange={(e) => setForm({ ...form, location: e.target.value })}
            placeholder="Where did it occur?"
          />
        </div>
        <Input
          label="Date & Time Occurred"
          type="datetime-local"
          value={form.date_occurred}
          onChange={(e) => setForm({ ...form, date_occurred: e.target.value })}
        />
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Reporter Name"
            required
            value={form.reported_by_name}
            onChange={(e) => setForm({ ...form, reported_by_name: e.target.value })}
            placeholder="Who is reporting?"
          />
          <Input
            label="Reporter Email"
            type="email"
            value={form.reported_by_email}
            onChange={(e) => setForm({ ...form, reported_by_email: e.target.value })}
            placeholder="Optional"
          />
        </div>

        {form.incident_type === 'safety' && (
          <div className="border border-zinc-800 rounded-lg p-3 space-y-3">
            <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Safety Details</p>
            <Input label="Injured Person" value={form.injured_person} onChange={(e) => setForm({ ...form, injured_person: e.target.value })} placeholder="Name of injured person" />
            <Input label="Body Parts (comma-separated)" value={form.body_parts} onChange={(e) => setForm({ ...form, body_parts: e.target.value })} placeholder="e.g. hand, wrist" />
            <div className="grid grid-cols-2 gap-3">
              <Input label="Injury Type" value={form.injury_type} onChange={(e) => setForm({ ...form, injury_type: e.target.value })} placeholder="e.g. cut, burn, strain" />
              <Select label="Treatment" options={[{ value: '', label: 'Select...' }, { value: 'first_aid', label: 'First Aid' }, { value: 'medical', label: 'Medical' }, { value: 'er', label: 'Emergency Room' }, { value: 'hospitalization', label: 'Hospitalization' }]} value={form.treatment} onChange={(e) => setForm({ ...form, treatment: e.target.value })} />
            </div>
            <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
              <input type="checkbox" checked={form.osha_recordable} onChange={(e) => setForm({ ...form, osha_recordable: e.target.checked })} className="rounded border-zinc-700 bg-zinc-900" />
              OSHA Recordable
            </label>
          </div>
        )}
        {form.incident_type === 'behavioral' && (
          <div className="border border-zinc-800 rounded-lg p-3 space-y-3">
            <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Behavioral Details</p>
            <Input label="Policy Violated" value={form.policy_violated} onChange={(e) => setForm({ ...form, policy_violated: e.target.value })} placeholder="Which policy was violated?" />
            <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
              <input type="checkbox" checked={form.manager_notified} onChange={(e) => setForm({ ...form, manager_notified: e.target.checked })} className="rounded border-zinc-700 bg-zinc-900" />
              Manager Notified
            </label>
          </div>
        )}
        {form.incident_type === 'property' && (
          <div className="border border-zinc-800 rounded-lg p-3 space-y-3">
            <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Property Details</p>
            <Input label="Asset Damaged" value={form.asset_damaged} onChange={(e) => setForm({ ...form, asset_damaged: e.target.value })} placeholder="What was damaged?" />
            <Input label="Estimated Cost ($)" type="number" value={form.estimated_cost} onChange={(e) => setForm({ ...form, estimated_cost: e.target.value })} placeholder="0.00" />
            <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
              <input type="checkbox" checked={form.insurance_claim} onChange={(e) => setForm({ ...form, insurance_claim: e.target.checked })} className="rounded border-zinc-700 bg-zinc-900" />
              Insurance Claim Filed
            </label>
          </div>
        )}
        {form.incident_type === 'near_miss' && (
          <div className="border border-zinc-800 rounded-lg p-3 space-y-3">
            <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Near Miss Details</p>
            <Input label="Potential Outcome" value={form.potential_outcome} onChange={(e) => setForm({ ...form, potential_outcome: e.target.value })} placeholder="What could have happened?" />
            <Input label="Hazard Identified" value={form.hazard_identified} onChange={(e) => setForm({ ...form, hazard_identified: e.target.value })} placeholder="What hazard was found?" />
          </div>
        )}

        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Witnesses</p>
            <button type="button" onClick={() => setWitnesses([...witnesses, { name: '', contact: '' }])} className="text-xs text-emerald-400 hover:text-emerald-300">+ Add Witness</button>
          </div>
          {witnesses.map((w, i) => (
            <div key={i} className="flex items-center gap-2 mb-2">
              <Input label="" placeholder="Name" value={w.name} onChange={(e) => { const copy = [...witnesses]; copy[i] = { ...copy[i], name: e.target.value }; setWitnesses(copy) }} className="flex-1" />
              <Input label="" placeholder="Contact" value={w.contact} onChange={(e) => { const copy = [...witnesses]; copy[i] = { ...copy[i], contact: e.target.value }; setWitnesses(copy) }} className="flex-1" />
              <button type="button" onClick={() => setWitnesses(witnesses.filter((_, j) => j !== i))} className="text-xs text-zinc-600 hover:text-red-400">&times;</button>
            </div>
          ))}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving}>{saving ? 'Submitting...' : 'Submit Report'}</Button>
        </div>
      </form>
    </Modal>
  )
}
