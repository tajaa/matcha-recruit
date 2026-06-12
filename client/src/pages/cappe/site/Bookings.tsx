import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Plus, Trash2, Calendar, Save } from 'lucide-react'
import { cappeApi } from '../../../api/cappeClient'
import SurfaceShell, { WEEKDAYS } from '../../../components/cappe/SurfaceShell'
import type { CappeBooking, CappeBookingType, CappeAvailabilitySlot } from '../../../types/cappe'

const hhmm = (t: string) => t.slice(0, 5)

const statusStyle: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-700',
  confirmed: 'bg-emerald-100 text-emerald-700',
  cancelled: 'bg-zinc-100 text-zinc-500',
  completed: 'bg-blue-100 text-blue-700',
}

export default function Bookings() {
  const { siteId } = useParams<{ siteId: string }>()
  const [types, setTypes] = useState<CappeBookingType[]>([])
  const [slots, setSlots] = useState<CappeAvailabilitySlot[]>([])
  const [bookings, setBookings] = useState<CappeBooking[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [typeForm, setTypeForm] = useState({ name: '', duration_minutes: '30' })
  const [savingAvail, setSavingAvail] = useState(false)

  useEffect(() => {
    Promise.all([
      cappeApi.get<CappeBookingType[]>(`/sites/${siteId}/booking-types`),
      cappeApi.get<CappeAvailabilitySlot[]>(`/sites/${siteId}/availability`),
      cappeApi.get<CappeBooking[]>(`/sites/${siteId}/bookings`),
    ])
      .then(([t, a, b]) => { setTypes(t); setSlots(a); setBookings(b) })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [siteId])

  async function addType(e: React.FormEvent) {
    e.preventDefault()
    if (!typeForm.name.trim()) return
    const created = await cappeApi.post<CappeBookingType>(`/sites/${siteId}/booking-types`, {
      name: typeForm.name.trim(),
      duration_minutes: parseInt(typeForm.duration_minutes, 10) || 30,
    })
    setTypes((t) => [...t, created])
    setTypeForm({ name: '', duration_minutes: '30' })
  }

  async function removeType(id: string) {
    await cappeApi.delete(`/sites/${siteId}/booking-types/${id}`)
    setTypes((t) => t.filter((x) => x.id !== id))
  }

  function addSlot() {
    setSlots((s) => [...s, { weekday: 0, start_time: '09:00', end_time: '17:00', booking_type_id: null }])
  }
  function setSlot(i: number, patch: Partial<CappeAvailabilitySlot>) {
    setSlots((s) => s.map((x, idx) => (idx === i ? { ...x, ...patch } : x)))
  }

  async function saveAvailability() {
    setSavingAvail(true)
    setError(null)
    try {
      const payload = { slots: slots.map((s) => ({ ...s, start_time: hhmm(s.start_time), end_time: hhmm(s.end_time) })) }
      const saved = await cappeApi.put<CappeAvailabilitySlot[]>(`/sites/${siteId}/availability`, payload)
      setSlots(saved)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save availability')
    } finally {
      setSavingAvail(false)
    }
  }

  async function setBookingStatus(b: CappeBooking, status: string) {
    const updated = await cappeApi.patch<CappeBooking>(`/sites/${siteId}/bookings/${b.id}`, { status })
    setBookings((list) => list.map((x) => (x.id === b.id ? updated : x)))
  }

  if (loading) {
    return <SurfaceShell title="Bookings"><div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-zinc-400" /></div></SurfaceShell>
  }

  return (
    <SurfaceShell title="Bookings" subtitle="Appointment types, availability, and requests.">
      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {/* Booking types */}
      <section className="mb-6 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-zinc-900">Appointment types</h2>
        <form onSubmit={addType} className="mb-3 flex flex-wrap gap-2">
          <input value={typeForm.name} onChange={(e) => setTypeForm({ ...typeForm, name: e.target.value })} placeholder="e.g. 30-min consult" className="flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-emerald-500" />
          <input value={typeForm.duration_minutes} onChange={(e) => setTypeForm({ ...typeForm, duration_minutes: e.target.value })} type="number" min="1" placeholder="min" className="w-24 rounded-lg border border-zinc-300 px-3 py-2 text-sm outline-none focus:border-emerald-500" />
          <button type="submit" className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700"><Plus className="h-4 w-4" /> Add</button>
        </form>
        {types.length === 0 ? (
          <p className="text-sm text-zinc-400">No appointment types yet.</p>
        ) : (
          <ul className="divide-y divide-zinc-100">
            {types.map((t) => (
              <li key={t.id} className="flex items-center justify-between py-2 text-sm">
                <span className="text-zinc-800">{t.name} <span className="text-zinc-400">· {t.duration_minutes} min</span></span>
                <button onClick={() => removeType(t.id)} className="text-zinc-400 hover:text-red-600"><Trash2 className="h-4 w-4" /></button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Availability */}
      <section className="mb-6 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-zinc-900">Weekly availability</h2>
        <div className="space-y-2">
          {slots.map((s, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <select value={s.weekday} onChange={(e) => setSlot(i, { weekday: parseInt(e.target.value, 10) })} className="rounded-lg border border-zinc-300 px-2 py-1.5 text-sm">
                {WEEKDAYS.map((d, idx) => <option key={idx} value={idx}>{d}</option>)}
              </select>
              <input type="time" value={hhmm(s.start_time)} onChange={(e) => setSlot(i, { start_time: e.target.value })} className="rounded-lg border border-zinc-300 px-2 py-1.5 text-sm" />
              <span className="text-zinc-400">to</span>
              <input type="time" value={hhmm(s.end_time)} onChange={(e) => setSlot(i, { end_time: e.target.value })} className="rounded-lg border border-zinc-300 px-2 py-1.5 text-sm" />
              <select value={s.booking_type_id ?? ''} onChange={(e) => setSlot(i, { booking_type_id: e.target.value || null })} className="rounded-lg border border-zinc-300 px-2 py-1.5 text-sm">
                <option value="">All types</option>
                {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
              <button type="button" onClick={() => setSlots((sl) => sl.filter((_, idx) => idx !== i))} className="text-zinc-400 hover:text-red-600"><Trash2 className="h-4 w-4" /></button>
            </div>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <button onClick={addSlot} className="text-xs font-medium text-emerald-700 hover:underline">+ Add window</button>
          <button onClick={saveAvailability} disabled={savingAvail} className="ml-auto flex items-center gap-1.5 rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-60">
            {savingAvail ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save availability
          </button>
        </div>
      </section>

      {/* Bookings */}
      <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-zinc-900">Requests</h2>
        {bookings.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-zinc-400"><Calendar className="h-4 w-4" /> No bookings yet.</p>
        ) : (
          <ul className="divide-y divide-zinc-100">
            {bookings.map((b) => (
              <li key={b.id} className="flex items-center gap-3 py-2 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-zinc-800">{b.customer_email || 'No email'}</div>
                  <div className="text-xs text-zinc-400">{new Date(b.starts_at).toLocaleString()}</div>
                </div>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[b.status]}`}>{b.status}</span>
                <select value={b.status} onChange={(e) => setBookingStatus(b, e.target.value)} className="rounded-lg border border-zinc-300 px-2 py-1 text-xs">
                  {['pending', 'confirmed', 'cancelled', 'completed'].map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </li>
            ))}
          </ul>
        )}
      </section>
    </SurfaceShell>
  )
}
