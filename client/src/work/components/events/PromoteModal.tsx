import { useState } from 'react'
import { Modal, Input, Select, Textarea } from '../../../components/ui'
import { INCIDENT_TYPE_OPTIONS, SEVERITY_OPTIONS } from '../../../types/ir'
import { promoteEvent, type EmsEvent } from '../../api/events'
import { ApiError } from '../../../api/client'

interface PromoteModalProps {
  event: EmsEvent
  onClose: () => void
  onPromoted: (incidentId: string) => void
}

/** `ems_events.created_at` (a real instant, timestamptz) -> the local
 *  wall-clock string a datetime-local input wants. */
function toDatetimeLocal(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function PromoteModal({ event, onClose, onPromoted }: PromoteModalProps) {
  const [title, setTitle] = useState(event.title ?? '')
  const [incidentType, setIncidentType] = useState(
    event.suggested_incident_type ?? (event.urgency === 'osha' ? 'safety' : 'other'))
  const [severity, setSeverity] = useState(
    event.urgency === 'osha' ? 'critical' : (event.suggested_severity ?? 'medium'))
  const [occurredAt, setOccurredAt] = useState(toDatetimeLocal(event.created_at))
  const [location, setLocation] = useState('')
  const [witnesses, setWitnesses] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit() {
    setSubmitting(true)
    setError(null)
    try {
      const witnessNames = witnesses
        .split(',')
        .map((w) => w.trim())
        .filter(Boolean)
      const { incident_id } = await promoteEvent(event.id, {
        title: title.trim() || undefined,
        incident_type: incidentType,
        severity,
        // Send the local wall-clock string VERBATIM, not .toISOString().
        // `ir_incidents.occurred_at` is TIMESTAMP *WITHOUT* TIME ZONE, and
        // every other IR intake path writes local wall-clock into it (the
        // manual form posts free-text `date_text`). Converting to UTC first
        // made asyncpg strip the offset on write, so an evening event west
        // of UTC landed on the incident dated a day ahead of the date this
        // very modal displayed.
        occurred_at: occurredAt || undefined,
        location: location.trim() || undefined,
        witnesses: witnessNames.length > 0 ? witnessNames : undefined,
      })
      onPromoted(incident_id)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('This event was already promoted or dismissed.')
      } else if (err instanceof ApiError && err.status === 403) {
        setError("You don't have permission to promote this event.")
      } else {
        setError(err instanceof Error ? err.message : 'Failed to promote event')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open onClose={onClose} title="Promote to Incident" width="md">
      <div className="space-y-4">
        <Input
          label="Title"
          id="promote-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={event.narrative.slice(0, 60)}
        />

        <div className="grid grid-cols-2 gap-3">
          <Select
            label="Incident type"
            id="promote-incident-type"
            options={INCIDENT_TYPE_OPTIONS}
            value={incidentType}
            onChange={(e) => setIncidentType(e.target.value)}
          />
          <Select
            label="Severity"
            id="promote-severity"
            options={SEVERITY_OPTIONS}
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          />
        </div>

        <Input
          label="Occurred at"
          id="promote-occurred-at"
          type="datetime-local"
          value={occurredAt}
          onChange={(e) => setOccurredAt(e.target.value)}
        />

        <Input
          label="Location"
          id="promote-location"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="Optional"
        />

        <Textarea
          label="Witnesses (comma-separated names)"
          id="promote-witnesses"
          rows={2}
          value={witnesses}
          onChange={(e) => setWitnesses(e.target.value)}
          placeholder="Optional"
        />

        {error && <p className="text-sm text-red-400">{error}</p>}

        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="rounded-lg bg-zinc-700 px-5 py-2 text-sm font-medium text-white hover:bg-zinc-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? 'Promoting…' : 'Promote'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
