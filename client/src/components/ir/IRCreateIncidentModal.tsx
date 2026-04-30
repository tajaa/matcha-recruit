import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { Button, Input, Modal, Select, Textarea } from '../ui'
import type { IRIncident, IRWitness } from '../../types/ir'

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
  involved_text: '',
  next_steps: '',
}

function locationLabel(loc: LocationRow): string {
  const name = (loc.name || '').trim()
  const place = [loc.city, loc.state].filter(Boolean).join(', ')
  if (name && place) return `${name} — ${place}`
  return name || place || loc.id.slice(0, 8)
}

// Split "Jane Doe, John Smith\nPat Lee" into ["Jane Doe", "John Smith", "Pat Lee"].
function parseInvolved(text: string): IRWitness[] {
  return text
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((name) => ({ name, contact: null }))
}

type Props = {
  open: boolean
  onClose: () => void
  onCreated: (incident: IRIncident) => void
}

export function IRCreateIncidentModal({ open, onClose, onCreated }: Props) {
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
      setSubmitError('Add a description so the AI can categorize the incident.')
      return
    }
    setSaving(true)
    try {
      const selectedLocation = (locations || []).find((l) => l.id === form.location_id)
      const witnesses = parseInvolved(form.involved_text)
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
        corrective_actions: form.next_steps.trim() || null,
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
          placeholder="What happened? Include relevant details — the AI will categorize from this."
        />

        <Textarea
          label="Name of all involved"
          value={form.involved_text}
          onChange={(e) => setForm({ ...form, involved_text: e.target.value })}
          placeholder="One name per line, or comma-separated"
        />

        <Textarea
          label="Recommended next steps (optional)"
          value={form.next_steps}
          onChange={(e) => setForm({ ...form, next_steps: e.target.value })}
          placeholder="Anything you'd like the team to do?"
        />

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
