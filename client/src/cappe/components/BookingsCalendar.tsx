import { useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Check, X, Clock, ShieldCheck } from 'lucide-react'
import { WEEKDAYS } from './SurfaceShell'
import type { CappeBooking, CappeAvailabilitySlot, CappeBookingType, CappeStaff } from '../types'
import { applicableSlotsForType } from '../utils/bookingAvailability'
import { bookingDateKey, formatBookingTime } from '../utils/bookingTime'

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const money = (c: number | null | undefined) => (c == null ? '—' : `$${(c / 100).toFixed(2)}`)
const hhmm = (t: string) => t.slice(0, 5)

// Calendar dates are logical dates in the selected business timezone. UTC date
// objects are used only for arithmetic so the browser timezone cannot shift them.
const pyWeekday = (d: Date) => (d.getUTCDay() + 6) % 7
const dateKey = (d: Date) => `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
const dateParts = (key: string) => {
  const [y, m, d] = key.split('-').map(Number)
  return { y, m: m - 1, d }
}
const dateFromKey = (key: string) => {
  const { y, m, d } = dateParts(key)
  return new Date(Date.UTC(y, m, d))
}

const dotColor: Record<string, string> = {
  pending: 'bg-amber-400',
  confirmed: 'bg-emerald-400',
  completed: 'bg-sky-400',
  declined: 'bg-red-400',
  cancelled: 'bg-zinc-600',
}
const statusStyle: Record<string, string> = {
  pending: 'bg-amber-500/15 text-amber-400',
  confirmed: 'bg-emerald-500/15 text-emerald-400',
  declined: 'bg-red-500/15 text-red-400',
  cancelled: 'bg-zinc-800 text-zinc-500',
  completed: 'bg-sky-500/15 text-sky-400',
}

type Props = {
  bookings: CappeBooking[]
  availability: CappeAvailabilitySlot[]
  types: CappeBookingType[]
  staff: CappeStaff[]
  onAccept: (b: CappeBooking) => void
  onDecline: (b: CappeBooking) => void
  onStatus: (b: CappeBooking, status: string) => void
  calendarTimezone: string
  timezoneForBooking: (booking: CappeBooking) => string
  allLocations: boolean
}

export default function BookingsCalendar({
  bookings, availability, types, staff, onAccept, onDecline, onStatus,
  calendarTimezone, timezoneForBooking, allLocations,
}: Props) {
  const todayKey = bookingDateKey(new Date().toISOString(), calendarTimezone)
  const todayParts = dateParts(todayKey)
  const [cursor, setCursor] = useState({ y: todayParts.y, m: todayParts.m })
  const [selected, setSelected] = useState<string>(todayKey)
  const [selectedTypeId, setSelectedTypeId] = useState('')

  useEffect(() => {
    const next = dateParts(bookingDateKey(new Date().toISOString(), calendarTimezone))
    setCursor({ y: next.y, m: next.m })
    setSelected(bookingDateKey(new Date().toISOString(), calendarTimezone))
  }, [calendarTimezone])

  const typeName = useMemo(() => {
    const map: Record<string, string> = {}
    types.forEach((t) => { map[t.id] = t.name })
    return map
  }, [types])

  const staffName = useMemo(() => {
    const map: Record<string, string> = {}
    staff.forEach((person) => { map[person.id] = person.name })
    return map
  }, [staff])

  const selectedType = types.find((type) => type.id === selectedTypeId)
  const calendarAvailability = selectedType ? applicableSlotsForType(availability, selectedType) : availability

  // Bookings grouped by local calendar day (skip cancelled/declined on the grid).
  const byDay = useMemo(() => {
    const m: Record<string, CappeBooking[]> = {}
    for (const b of bookings) {
      if (b.status === 'cancelled' || b.status === 'declined') continue
      const k = bookingDateKey(b.starts_at, timezoneForBooking(b))
      ;(m[k] ||= []).push(b)
    }
    Object.values(m).forEach((list) => list.sort((a, z) => +new Date(a.starts_at) - +new Date(z.starts_at)))
    return m
  }, [bookings, timezoneForBooking])

  // Availability windows grouped by Python weekday.
  const availByWeekday = useMemo(() => {
    const m: Record<number, CappeAvailabilitySlot[]> = {}
    for (const s of calendarAvailability) (m[s.weekday] ||= []).push(s)
    return m
  }, [calendarAvailability])

  const daysInMonth = new Date(Date.UTC(cursor.y, cursor.m + 1, 0)).getUTCDate()
  const leadBlanks = pyWeekday(new Date(Date.UTC(cursor.y, cursor.m, 1)))
  const cells: (number | null)[] = [
    ...Array(leadBlanks).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ]
  while (cells.length % 7 !== 0) cells.push(null)

  const move = (delta: number) => {
    const d = new Date(Date.UTC(cursor.y, cursor.m + delta, 1))
    setCursor({ y: d.getUTCFullYear(), m: d.getUTCMonth() })
  }

  const selectedDate = useMemo(() => {
    return dateFromKey(selected)
  }, [selected])
  const selectedBookings = byDay[selected] || []
  const selectedAvail = availByWeekday[pyWeekday(selectedDate)] || []

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
      {/* calendar */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-zinc-100">{MONTHS[cursor.m]} {cursor.y}</h3>
          <div className="flex items-center gap-1">
            <button onClick={() => setCursor({ y: todayParts.y, m: todayParts.m })} className="rounded-lg border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800">Today</button>
            <button onClick={() => move(-1)} className="rounded-lg border border-zinc-700 p-1 text-zinc-300 hover:bg-zinc-800"><ChevronLeft className="h-4 w-4" /></button>
            <button onClick={() => move(1)} className="rounded-lg border border-zinc-700 p-1 text-zinc-300 hover:bg-zinc-800"><ChevronRight className="h-4 w-4" /></button>
          </div>
        </div>
        <select value={selectedTypeId} onChange={(event) => setSelectedTypeId(event.target.value)} className="mb-3 rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-200">
          <option value="">All appointment types</option>
          {types.filter((type) => type.status === 'active').map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}
        </select>
        <div className="grid grid-cols-7 gap-px overflow-hidden rounded-xl border border-zinc-800 bg-zinc-800 text-center">
          {WEEKDAYS.map((d) => (
            <div key={d} className="bg-zinc-900 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">{d}</div>
          ))}
          {cells.map((day, i) => {
            if (day == null) return <div key={i} className="min-h-[68px] bg-zinc-950/40" />
            const k = dateKey(new Date(Date.UTC(cursor.y, cursor.m, day)))
            const dayBookings = byDay[k] || []
            const hasAvail = (availByWeekday[pyWeekday(new Date(Date.UTC(cursor.y, cursor.m, day)))] || []).length > 0
            const isToday = k === todayKey
            const isSel = k === selected
            return (
              <button
                key={i}
                onClick={() => setSelected(k)}
                className={`min-h-[68px] bg-zinc-900 p-1.5 text-left align-top transition hover:bg-zinc-800/70 ${isSel ? 'ring-1 ring-inset ring-emerald-500' : ''}`}
              >
                <div className="flex items-center justify-between">
                  <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-xs ${isToday ? 'bg-emerald-500 font-bold text-zinc-950' : 'text-zinc-400'}`}>{day}</span>
                  {hasAvail && <span className="h-1.5 w-1.5 rounded-full bg-emerald-500/40" title="Available this day" />}
                </div>
                <div className="mt-1 space-y-0.5">
                  {dayBookings.slice(0, 2).map((b) => (
                    <div key={b.id} className="flex items-center gap-1 truncate text-[10px] text-zinc-300">
                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotColor[b.status] || 'bg-zinc-500'}`} />
                      <span className="truncate">{formatBookingTime(b.starts_at, timezoneForBooking(b))}</span>
                    </div>
                  ))}
                  {dayBookings.length > 2 && <div className="text-[10px] text-zinc-500">+{dayBookings.length - 2} more</div>}
                </div>
              </button>
            )
          })}
        </div>
        <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-zinc-500">
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-400" /> Confirmed</span>
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-400" /> Pending</span>
          <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-sky-400" /> Completed</span>
          <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500/40" /> Open for booking</span>
        </div>
        <p className="mt-2 text-[11px] text-zinc-500">
          {allLocations ? 'Bookings use each location’s local time.' : `Times in ${calendarTimezone}.`}
        </p>
      </div>

      {/* day detail */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4">
        <h3 className="text-sm font-semibold text-zinc-100">
          {new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', weekday: 'long', month: 'short', day: 'numeric' }).format(selectedDate)}
        </h3>

        {selectedAvail.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {selectedAvail.map((s, i) => (
              <span key={i} className="inline-flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-300">
                 <Clock className="h-3 w-3" /> {hhmm(s.start_time)}–{hhmm(s.end_time)}
                 {s.booking_type_id ? ` · ${typeName[s.booking_type_id] || 'type'}` : ''}
                 {s.staff_id ? ` · ${staffName[s.staff_id] || 'staff'}` : ' · Any staff'}
               </span>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-xs text-zinc-500">Not open for booking this day.</p>
        )}

        <div className="mt-4 space-y-2">
          {selectedBookings.length === 0 ? (
            <p className="text-xs text-zinc-500">No bookings.</p>
          ) : (
            selectedBookings.map((b) => {
              const isPendingApproval = b.status === 'pending' && b.requires_approval
              return (
                <div key={b.id} className="rounded-lg border border-zinc-800 bg-zinc-900 p-2.5 text-sm">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-zinc-100">{b.customer_name || b.customer_email || 'Customer'}</div>
                      <div className="text-xs text-zinc-400">
                        {formatBookingTime(b.starts_at, timezoneForBooking(b))}
                        –{formatBookingTime(b.ends_at, timezoneForBooking(b))}
                        {allLocations && (b.location_name || timezoneForBooking(b)) ? ` · ${b.location_name || timezoneForBooking(b)}` : ''}
                        {b.booking_type_id && typeName[b.booking_type_id] ? ` · ${typeName[b.booking_type_id]}` : ''}
                        {b.staff_name ? ` · ${b.staff_name}` : ''}
                        {' · '}<span className="text-emerald-400">{money(b.quoted_price_cents)}</span>
                      </div>
                      {b.rider_acknowledged && <div className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-zinc-500"><ShieldCheck className="h-3 w-3" /> agreed to rider</div>}
                    </div>
                    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[b.status]}`}>{b.status}</span>
                  </div>
                  {isPendingApproval ? (
                    <div className="mt-2 flex gap-1.5">
                      <button onClick={() => onAccept(b)} className="flex items-center gap-1 rounded-md bg-emerald-500 px-2.5 py-1 text-xs font-semibold text-zinc-950 hover:bg-emerald-400"><Check className="h-3 w-3" /> Accept</button>
                      <button onClick={() => onDecline(b)} className="flex items-center gap-1 rounded-md border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800"><X className="h-3 w-3" /> Decline</button>
                    </div>
                  ) : (
                    <select value={b.status} onChange={(e) => onStatus(b, e.target.value)} className="mt-2 rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100">
                      {['pending', 'confirmed', 'cancelled', 'completed'].map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  )}
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
