import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { Button, Input, Modal, Select, Textarea } from '../ui'
import { IRPersonMultiSelect } from './IRPersonMultiSelect'
import { EmployeeMultiSelect } from '../employees/EmployeeMultiSelect'
import { useMe } from '../../hooks/useMe'
import type { IRIncident } from '../../types/ir'

type LocationRow = {
  id: string
  name: string | null
  city: string
  state: string
  is_active: boolean
}

const EMPTY_FORM = {
  reported_by_name: '',
  date_text: '',
  location_id: '',
  description: '',
  involved: [] as string[],
  involved_employee_ids: [] as string[],
  next_steps: '',
  withhold_name: false,
  intimate_injury: false,
  from_sexual_assault: false,
  contaminated_sharps: false,
  infectious_agent: 'none',
}

function locationLabel(loc: LocationRow): string {
  const name = (loc.name || '').trim()
  const place = [loc.city, loc.state].filter(Boolean).join(', ')
  if (name && place) return `${name} — ${place}`
  return name || place || loc.id.slice(0, 8)
}

type Props = {
  open: boolean
  onClose: () => void
  onCreated: (incident: IRIncident) => void
}

export function IRCreateIncidentModal({ open, onClose, onCreated }: Props) {
  const { hasFeature } = useMe()
  const hasRoster = hasFeature('employees')
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [locations, setLocations] = useState<LocationRow[] | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    api.get<LocationRow[]>('/ir-onboarding/locations')
      .then((rows) => {
        if (cancelled) return
        const active = (rows || []).filter((r) => r.is_active)
        setLocations(active)
        if (active.length === 1) {
          setForm((f) => (f.location_id ? f : { ...f, location_id: active[0].id }))
        }
      })
      .catch(() => {
        if (!cancelled) setLocations([])
      })
    return () => {
      cancelled = true
    }
  }, [open])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSubmitError(null)
    if (!form.location_id) {
      setSubmitError('Pick a location for this incident.')
      return
    }
    if (!form.description.trim()) {
      setSubmitError('Add a description so Intelligent Theme Analysis can categorize the incident.')
      return
    }
    setSaving(true)
    try {
      const selectedLocation = (locations || []).find((l) => l.id === form.location_id)
      const witnesses = form.involved.map((name) => ({ name, contact: null }))
      // OSHA Privacy Case signals → category_data; the backend's deterministic
      // rule masks the employee name on the 300/301 log. (AI also auto-detects
      // these from the description after submit; merge keeps these manual values.)
      const categoryData: Record<string, unknown> = {}
      if (form.intimate_injury) categoryData.intimate_injury = true
      if (form.from_sexual_assault) categoryData.from_sexual_assault = true
      if (form.contaminated_sharps) categoryData.contaminated_sharps = true
      if (form.infectious_agent !== 'none') categoryData.infectious_agent = form.infectious_agent
      if (form.withhold_name) categoryData.employee_privacy_requested = true
      const created = await api.post<IRIncident>('/ir/incidents', {
        description: form.description.trim(),
        // Free-text date — backend parses with dateutil and falls back to NOW().
        // Empty string also falls back to NOW().
        occurred_at: form.date_text.trim(),
        location_id: form.location_id,
        // Mirror to the legacy free-text column so the IR list + OSHA exports
        // keep showing a human-readable location string.
        location: selectedLocation ? locationLabel(selectedLocation) : null,
        reported_by_name: form.reported_by_name.trim() || 'Unknown',
        witnesses,
        involved_employee_ids: form.involved_employee_ids,
        corrective_actions: form.next_steps.trim() || null,
        // OSHA Privacy Case signals (assembled above) ride in category_data.
        category_data: Object.keys(categoryData).length ? categoryData : undefined,
      })
      setForm(EMPTY_FORM)
      onCreated(created)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to submit incident'
      setSubmitError(msg)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Report Incident">
      <form onSubmit={handleCreate} className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
        <Input
          label="Your name"
          required
          value={form.reported_by_name}
          onChange={(e) => setForm({ ...form, reported_by_name: e.target.value })}
          placeholder="Who is reporting?"
        />

        <Input
          label="Date and time of incident"
          required
          value={form.date_text}
          onChange={(e) => setForm({ ...form, date_text: e.target.value })}
          placeholder="e.g. yesterday around 3pm, May 1 at 9am"
        />

        {locations === null ? (
          <Input label="Location" value="Loading..." onChange={() => undefined} disabled />
        ) : locations.length === 0 ? (
          <div>
            <span className="text-xs text-zinc-400 uppercase tracking-wide">Location</span>
            <div className="mt-1 text-sm text-zinc-300 bg-zinc-900 border border-zinc-800 rounded px-3 py-2">
              No locations yet.{' '}
              <Link to="/app/locations" className="text-emerald-400 hover:text-emerald-300 underline">
                Add one
              </Link>{' '}
              before submitting an incident.
            </div>
          </div>
        ) : (
          <Select
            label="Location"
            required
            options={[
              { value: '', label: 'Select location...' },
              ...locations.map((l) => ({ value: l.id, label: locationLabel(l) })),
            ]}
            value={form.location_id}
            onChange={(e) => setForm({ ...form, location_id: e.target.value })}
          />
        )}

        <Textarea
          label="Description"
          required
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          placeholder="What happened? Include relevant details — Intelligent Theme Analysis will categorize from this."
        />

        {/* Roster link — only for tenants with an employee roster (CSV/HRIS).
            Sends employee UUIDs in involved_employee_ids; resolved server-side.
            Separate from the free-text witnesses field below. */}
        {hasRoster && (
          <EmployeeMultiSelect
            label="Involved employees (roster)"
            value={form.involved_employee_ids}
            onChange={(involved_employee_ids) => setForm({ ...form, involved_employee_ids })}
            placeholder="Search employees…"
          />
        )}

        {/* These names persist to the witnesses column (role=witness in the
            per-person index). Label says "witnesses / others involved" so the
            form matches the role taxonomy shown on a person's history. */}
        <IRPersonMultiSelect
          label="Witnesses / others involved"
          value={form.involved}
          onChange={(involved) => setForm({ ...form, involved })}
          placeholder="Type a name, Enter to add"
        />

        <Textarea
          label="Recommended next steps (optional)"
          value={form.next_steps}
          onChange={(e) => setForm({ ...form, next_steps: e.target.value })}
          placeholder="Anything you'd like the team to do?"
        />

        {/* OSHA Privacy Case signals (29 CFR 1904.29). Any of these masks the
            employee name on the posted 300/301 log. Optional — AI also
            auto-detects them from the description after submit; these manual
            values win over the AI. */}
        <div className="border border-white/10 rounded-lg p-3 space-y-2.5">
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
            Sensitive case (optional)
          </span>
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.intimate_injury}
              onChange={(e) => setForm({ ...form, intimate_injury: e.target.checked })}
              className="mt-0.5 accent-emerald-600"
            />
            <span className="text-xs text-zinc-400">Injury to an intimate or reproductive body part</span>
          </label>
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.from_sexual_assault}
              onChange={(e) => setForm({ ...form, from_sexual_assault: e.target.checked })}
              className="mt-0.5 accent-emerald-600"
            />
            <span className="text-xs text-zinc-400">Resulted from a sexual assault</span>
          </label>
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.contaminated_sharps}
              onChange={(e) => setForm({ ...form, contaminated_sharps: e.target.checked })}
              className="mt-0.5 accent-emerald-600"
            />
            <span className="text-xs text-zinc-400">Needlestick / cut from a contaminated sharp</span>
          </label>
          <Select
            label="Infectious exposure"
            options={[
              { value: 'none', label: 'None' },
              { value: 'hiv', label: 'HIV' },
              { value: 'hepatitis', label: 'Hepatitis' },
              { value: 'tuberculosis', label: 'Tuberculosis' },
              { value: 'other', label: 'Other' },
            ]}
            value={form.infectious_agent}
            onChange={(e) => setForm({ ...form, infectious_agent: e.target.value })}
          />
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.withhold_name}
              onChange={(e) => setForm({ ...form, withhold_name: e.target.checked })}
              className="mt-0.5 accent-emerald-600"
            />
            <span className="text-xs text-zinc-400">
              Employee requests their name be withheld (illness opt-out)
            </span>
          </label>
        </div>

        {submitError && <p className="text-sm text-red-400">{submitError}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving || !form.location_id}>
            {saving ? 'Submitting...' : 'Submit Report'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
