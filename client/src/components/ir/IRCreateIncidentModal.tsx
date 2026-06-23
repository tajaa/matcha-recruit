import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Mic, Square, Loader2 } from 'lucide-react'
import { api } from '../../api/client'
import { Button, Input, Modal, Select, Textarea } from '../ui'
import { IRPersonMultiSelect } from './IRPersonMultiSelect'
import { EmployeeMultiSelect } from '../employees/EmployeeMultiSelect'
import { useMe } from '../../hooks/useMe'
import { useVoiceDictation } from '../../hooks/ir/useVoiceDictation'
import type { IRIncident, VoicePrefill } from '../../types/ir'

type LocationRow = {
  id: string
  name: string | null
  city: string
  state: string
  is_active: boolean
}

// Intake stays strictly factual — reporter, when, where, what, who.
// OSHA recordability + Privacy Case are decided afterward in the IR Copilot
// (only recordable incidents reach a log), so no sensitive-case fields here.
const EMPTY_FORM = {
  reported_by_name: '',
  date_text: '',
  location_id: '',
  description: '',
  involved: [] as string[],
  involved_employee_ids: [] as string[],
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

function fmtElapsed(s: number): string {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function IRCreateIncidentModal({ open, onClose, onCreated }: Props) {
  const { hasFeature } = useMe()
  const hasRoster = hasFeature('employees')
  const canDictate = hasFeature('ir_voice_intake')
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [locations, setLocations] = useState<LocationRow[] | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [transcribing, setTranscribing] = useState(false)
  const [voiceMsg, setVoiceMsg] = useState<string | null>(null)
  const [voiceHint, setVoiceHint] = useState<{ type?: string; severity?: string } | null>(null)

  // declared before the hook so onMaxDuration can call it
  async function finishDictation() {
    const wav = await dictation.stop()
    if (!wav) { setVoiceMsg('No audio captured — try again.'); return }
    setTranscribing(true)
    setVoiceMsg(null)
    try {
      const fd = new FormData()
      fd.append('file', wav, 'dictation.wav')
      const p = await api.upload<VoicePrefill>('/ir/incidents/voice/parse', fd)
      if (!p.available) { setVoiceMsg("Couldn't understand the audio — please type the details."); return }
      setForm((f) => ({
        ...f,
        description: p.description ?? f.description,
        reported_by_name: p.reported_by_name ?? f.reported_by_name,
        date_text: p.occurred_at_text ?? f.date_text,
        location_id: p.location_id && (locations || []).some((l) => l.id === p.location_id) ? p.location_id : f.location_id,
        involved: p.witnesses?.length
          ? Array.from(new Set([...f.involved, ...p.witnesses.map((w) => w.name)]))
          : f.involved,
      }))
      setVoiceHint(p.incident_type || p.severity ? { type: p.incident_type ?? undefined, severity: p.severity ?? undefined } : null)
    } catch {
      setVoiceMsg('Transcription failed — please type the details.')
    } finally {
      setTranscribing(false)
    }
  }

  const dictation = useVoiceDictation({ maxDurationSeconds: 120, onMaxDuration: () => { void finishDictation() } })

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

        {canDictate && (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2.5 space-y-1.5">
            <div className="flex items-center gap-2 flex-wrap">
              {dictation.status === 'recording' ? (
                <button type="button" onClick={() => { void finishDictation() }}
                  className="inline-flex items-center gap-1.5 text-sm text-red-400 px-2.5 py-1 rounded-lg border border-red-500/40 hover:border-red-400">
                  <Square className="h-3.5 w-3.5 fill-current" /> Stop · {fmtElapsed(dictation.elapsedSeconds)}
                </button>
              ) : transcribing ? (
                <span className="inline-flex items-center gap-1.5 text-sm text-zinc-400"><Loader2 className="h-4 w-4 animate-spin" /> Transcribing…</span>
              ) : (
                <button type="button" onClick={() => { setVoiceMsg(null); setVoiceHint(null); void dictation.start() }}
                  className="inline-flex items-center gap-1.5 text-sm text-zinc-200 px-2.5 py-1 rounded-lg border border-zinc-700 hover:border-zinc-500">
                  <Mic className="h-4 w-4" /> Dictate
                </button>
              )}
              {dictation.status === 'recording' && <span className="text-xs text-red-400 animate-pulse">● recording</span>}
            </div>
            <p className="text-[11px] text-zinc-500">AI-assisted — review every field before submitting. This is a legal record.</p>
            {dictation.status === 'denied' && <p className="text-[11px] text-amber-400">Microphone access denied — enable it in your browser settings, or just type the report.</p>}
            {dictation.status === 'error' && <p className="text-[11px] text-amber-400">Couldn't start recording — please type the report.</p>}
            {voiceMsg && <p className="text-[11px] text-amber-400">{voiceMsg}</p>}
            {voiceHint && (
              <p className="text-[11px] text-zinc-400">Suggested: {[voiceHint.type, voiceHint.severity].filter(Boolean).join(' · ')} <span className="text-zinc-600">(AI — finalized after submit)</span></p>
            )}
          </div>
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
            Each roster employee becomes their own injured-person row on the OSHA
            300 log. Separate from the free-text witnesses field below. */}
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
