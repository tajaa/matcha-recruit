import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Mic, Square, Loader2, Sparkles, AlertTriangle } from 'lucide-react'
import { api } from '../../api/client'
import { Button, Modal, Select } from '../ui'
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

// Shared field chrome — matches the /app micro-label + control look (see IRDetail
// + the Select primitive) so the modal reads as one cohesive surface.
const LABEL = 'block text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1.5'
const FIELD =
  'w-full rounded-lg border border-white/[0.08] bg-zinc-900 px-3 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none hover:border-white/15 focus:border-white/25 focus:ring-1 focus:ring-white/10 transition-colors'

function Field({ label, required, children }: { label: string; required?: boolean; children: ReactNode }) {
  return (
    <div>
      <label className={LABEL}>
        {label}
        {required && <span className="text-red-400 ml-1">*</span>}
      </label>
      {children}
    </div>
  )
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
  // Set when dictation finished but didn't capture a location and there's more than
  // one to choose from — we ask the reporter to pick (or re-dictate saying it).
  const [locationMissing, setLocationMissing] = useState(false)

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
      const voiceLoc = p.location_id && (locations || []).some((l) => l.id === p.location_id) ? p.location_id : null
      setForm((f) => ({
        ...f,
        description: p.description ?? f.description,
        reported_by_name: p.reported_by_name ?? f.reported_by_name,
        date_text: p.occurred_at_text ?? f.date_text,
        location_id: voiceLoc ?? f.location_id,
        involved: p.witnesses?.length
          ? Array.from(new Set([...f.involved, ...p.witnesses.map((w) => w.name)]))
          : f.involved,
      }))
      setVoiceHint(p.incident_type || p.severity ? { type: p.incident_type ?? undefined, severity: p.severity ?? undefined } : null)
      // If voice didn't pin a location (and one wasn't already chosen), ask for it —
      // only meaningful when there's a choice to make.
      setLocationMissing(!voiceLoc && !form.location_id && (locations?.length ?? 0) > 1)
    } catch (err) {
      const tooMany = err instanceof Error && err.message.startsWith('429')
      setVoiceMsg(tooMany
        ? 'Too many dictation attempts — wait a moment, or just type the details.'
        : 'Transcription failed — please type the details.')
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
    <Modal open={open} onClose={onClose} title="Report an incident">
      <p className="-mt-2 mb-5 text-[13px] text-zinc-400">
        Capture what happened — Intelligent Theme Analysis categorizes the rest after you submit.
      </p>
      <form onSubmit={handleCreate} className="space-y-5 max-h-[68vh] overflow-y-auto pr-1.5">
        {canDictate && (
          <div className="space-y-2">
            {dictation.status === 'recording' ? (
              <div className="flex items-center gap-3 rounded-xl border border-red-500/40 bg-red-500/[0.07] px-4 py-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-red-500/20 text-red-300 animate-pulse">
                  <Mic className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-zinc-100">Recording · {fmtElapsed(dictation.elapsedSeconds)}</div>
                  <div className="text-[12px] text-red-300/80">Say who, what, when, where, and who saw it.</div>
                </div>
                <button type="button" onClick={() => { void finishDictation() }}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-red-400/50 px-3 py-1.5 text-sm text-red-200 hover:bg-red-500/15 transition-colors">
                  <Square className="h-3.5 w-3.5 fill-current" /> Stop
                </button>
              </div>
            ) : transcribing ? (
              <div className="flex items-center gap-3 rounded-xl border border-white/[0.08] bg-zinc-800/40 px-4 py-3 text-sm text-zinc-300">
                <Loader2 className="h-4 w-4 animate-spin text-emerald-400" /> Transcribing & filling the form…
              </div>
            ) : (
              <button type="button" onClick={() => { setVoiceMsg(null); setVoiceHint(null); setLocationMissing(false); void dictation.start() }}
                className="group flex w-full items-center gap-3 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.06] px-4 py-3 text-left transition-colors hover:border-emerald-500/40 hover:bg-emerald-500/[0.1]">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-300 transition-colors group-hover:bg-emerald-500/25">
                  <Mic className="h-4 w-4" />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-zinc-100">Dictate this report</span>
                  <span className="block text-[12px] text-zinc-400">Talk it through — AI fills the form. You review every field before submitting.</span>
                </span>
              </button>
            )}

            <p className="px-0.5 text-[11px] text-zinc-500">AI-assisted — every field stays editable. This becomes a legal record.</p>
            {dictation.status === 'denied' && <p className="px-0.5 text-[11px] text-amber-400">Microphone access denied — enable it in your browser settings, or just type the report below.</p>}
            {dictation.status === 'error' && <p className="px-0.5 text-[11px] text-amber-400">Couldn't start recording — please type the report below.</p>}
            {voiceMsg && <p className="px-0.5 text-[11px] text-amber-400">{voiceMsg}</p>}
            {voiceHint && (
              <div className="inline-flex items-center gap-1.5 rounded-md border border-emerald-500/20 bg-emerald-500/[0.06] px-2 py-1 text-[11px] text-emerald-300">
                <Sparkles className="h-3 w-3" />
                AI suggestion: {[voiceHint.type, voiceHint.severity].filter(Boolean).join(' · ')}
                <span className="text-emerald-400/50">· confirmed after submit</span>
              </div>
            )}
          </div>
        )}

        {canDictate && (
          <div className="flex items-center gap-3 pt-0.5">
            <div className="h-px flex-1 bg-white/[0.06]" />
            <span className="text-[10px] font-medium uppercase tracking-[0.16em] text-zinc-600">Incident details</span>
            <div className="h-px flex-1 bg-white/[0.06]" />
          </div>
        )}

        <Field label="Your name" required>
          <input
            className={FIELD}
            value={form.reported_by_name}
            onChange={(e) => setForm({ ...form, reported_by_name: e.target.value })}
            placeholder="Who is reporting?"
          />
        </Field>

        <Field label="Date and time of incident" required>
          <input
            className={FIELD}
            value={form.date_text}
            onChange={(e) => setForm({ ...form, date_text: e.target.value })}
            placeholder="e.g. yesterday around 3pm, May 1 at 9am"
          />
        </Field>

        {locations === null ? (
          <Field label="Location">
            <input className={`${FIELD} opacity-50`} value="Loading…" disabled />
          </Field>
        ) : locations.length === 0 ? (
          <Field label="Location">
            <div className="rounded-lg border border-white/[0.08] bg-zinc-900 px-3 py-2.5 text-sm text-zinc-300">
              No locations yet.{' '}
              <Link to="/app/locations" className="text-emerald-400 hover:text-emerald-300 underline">Add one</Link>{' '}
              before submitting an incident.
            </div>
          </Field>
        ) : (
          <div>
            <Field label="Location" required>
              <Select
                className={locationMissing ? 'rounded-lg ring-1 ring-amber-500/50' : ''}
                options={[
                  { value: '', label: 'Select location…' },
                  ...locations.map((l) => ({ value: l.id, label: locationLabel(l) })),
                ]}
                value={form.location_id}
                onChange={(e) => { setForm({ ...form, location_id: e.target.value }); if (e.target.value) setLocationMissing(false) }}
              />
            </Field>
            {locationMissing && (
              <p className="mt-1.5 flex items-start gap-1.5 text-[11px] text-amber-400">
                <AlertTriangle className="mt-px h-3 w-3 shrink-0" />
                <span>We didn't catch the location from your recording — pick it above, or re-dictate and say where it happened.</span>
              </p>
            )}
          </div>
        )}

        <Field label="Description" required>
          <textarea
            className={`${FIELD} min-h-[96px] resize-y`}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="What happened? Include relevant details — Intelligent Theme Analysis will categorize from this."
          />
        </Field>

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
        <div className="flex justify-end gap-2 border-t border-white/[0.06] pt-4">
          <Button variant="ghost" type="button" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving || !form.location_id}>
            {saving ? 'Submitting…' : 'Submit report'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
