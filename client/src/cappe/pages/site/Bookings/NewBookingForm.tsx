import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { cappeApi } from '../../../api'
import type { CappeBooking, CappeBookingType, CappeLocation, CappeStaff } from '../../../types'
import { inputCls } from './constants'

// The owner books someone in — a phone call, a walk-in. The server skips the
// service's notice, horizon, opening hours and time off for these (the owner
// knows when they can see someone) but still refuses a double booking. Times
// are the store's (or the location's) local time.
export function NewBookingForm({ siteId, types, staff, locations, defaultLocation, onBooked, onCancel }: {
  siteId: string
  types: CappeBookingType[]
  staff: CappeStaff[]
  locations: CappeLocation[]
  defaultLocation: string
  onBooked: (b: CappeBooking) => void
  onCancel: () => void
}) {
  const bookable = types.filter((t) => t.status === 'active')
  const [typeId, setTypeId] = useState(bookable[0]?.id ?? '')
  const type = bookable.find((t) => t.id === typeId)
  const people = staff.filter((s) => s.active && (type?.staff_ids ?? []).includes(s.id))
  const [staffId, setStaffId] = useState('')
  const [locationId, setLocationId] = useState(defaultLocation)
  const [when, setWhen] = useState('')
  const [until, setUntil] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [note, setNote] = useState('')
  const [notify, setNotify] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const active = locations.filter((l) => l.active)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!type) { setError('Add a service first'); return }
    if (!when) { setError('Pick a date and time'); return }
    if (!name.trim()) { setError('Who is it for?'); return }
    if (people.length > 0 && !staffId) { setError('Choose who will see them'); return }
    setSaving(true); setError(null)
    try {
      const booked = await cappeApi.post<CappeBooking>(`/sites/${siteId}/bookings`, {
        booking_type_id: type.id, starts_at: when,
        ...(type.pricing_mode === 'hourly' && until ? { ends_at: until } : {}),
        staff_id: staffId || null,
        location_id: type.location_id ?? (locationId || null),
        customer_name: name.trim(), customer_email: email.trim() || null,
        note: note.trim() || null, notify: notify && !!email.trim(),
      })
      onBooked(booked)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not book it')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} aria-label="Book someone in" className="mb-4 grid gap-2 rounded-lg border border-zinc-700 bg-zinc-950/60 p-3 sm:grid-cols-2">
      <label className="text-xs text-zinc-400">Service
        <select value={typeId} onChange={(e) => { setTypeId(e.target.value); setStaffId('') }} className={`mt-1 w-full ${inputCls}`}>
          {bookable.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </label>
      {people.length > 0 ? (
        <label className="text-xs text-zinc-400">With
          <select value={staffId} onChange={(e) => setStaffId(e.target.value)} className={`mt-1 w-full ${inputCls}`}>
            <option value="">Choose…</option>
            {people.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
      ) : active.length > 0 && !type?.location_id ? (
        <label className="text-xs text-zinc-400">Location
          <select value={locationId} onChange={(e) => setLocationId(e.target.value)} className={`mt-1 w-full ${inputCls}`}>
            {active.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </label>
      ) : <div />}
      <label className="text-xs text-zinc-400">Starts
        <input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} className={`mt-1 w-full ${inputCls}`} />
      </label>
      {type?.pricing_mode === 'hourly' ? (
        <label className="text-xs text-zinc-400">Ends (optional)
          <input type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)} className={`mt-1 w-full ${inputCls}`} />
        </label>
      ) : <div />}
      <label className="text-xs text-zinc-400">Customer name
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={255} className={`mt-1 w-full ${inputCls}`} />
      </label>
      <label className="text-xs text-zinc-400">Email (optional)
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={`mt-1 w-full ${inputCls}`} />
      </label>
      <label className="text-xs text-zinc-400 sm:col-span-2">Note (optional)
        <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} className={`mt-1 w-full ${inputCls}`} />
      </label>
      {email.trim() && (
        <label className="flex items-center gap-2 text-xs text-zinc-300 sm:col-span-2">
          <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} /> Email them a confirmation
        </label>
      )}
      <p className="text-xs text-zinc-500 sm:col-span-2">Your own bookings aren’t held to opening hours, notice or time off — but can’t double-book.</p>
      {error && <p role="alert" className="text-xs text-red-400 sm:col-span-2">{error}</p>}
      <div className="flex gap-2 sm:col-span-2">
        <button type="submit" disabled={saving} className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
          {saving && <Loader2 className="h-4 w-4 animate-spin" />} Book it
        </button>
        <button type="button" onClick={onCancel} className="rounded-lg border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800">Cancel</button>
      </div>
    </form>
  )
}
