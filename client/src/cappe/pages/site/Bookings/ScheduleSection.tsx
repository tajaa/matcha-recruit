import type { Dispatch, SetStateAction } from 'react'
import { Calendar, List } from 'lucide-react'
import BookingsCalendar from '../../../components/BookingsCalendar'
import type { CappeBooking, CappeBookingType, CappeAvailabilitySlot } from '../../../types'
import { money, statusStyle } from './constants'

interface ScheduleSectionProps {
  view: 'calendar' | 'list'
  setView: Dispatch<SetStateAction<'calendar' | 'list'>>
  bookings: CappeBooking[]
  slots: CappeAvailabilitySlot[]
  types: CappeBookingType[]
  acceptBooking: (b: CappeBooking) => void
  declineBooking: (b: CappeBooking) => void
  setBookingStatus: (b: CappeBooking, status: string) => void
}

export function ScheduleSection({
  view, setView, bookings, slots, types, acceptBooking, declineBooking, setBookingStatus,
}: ScheduleSectionProps) {
  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-100">Your schedule</h2>
        <div className="flex items-center gap-0.5 rounded-lg border border-zinc-700 p-0.5">
          <button onClick={() => setView('calendar')} className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium ${view === 'calendar' ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}><Calendar className="h-3.5 w-3.5" /> Calendar</button>
          <button onClick={() => setView('list')} className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium ${view === 'list' ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}><List className="h-3.5 w-3.5" /> List</button>
        </div>
      </div>
      {view === 'calendar' ? (
        <BookingsCalendar bookings={bookings} availability={slots} types={types} onAccept={acceptBooking} onDecline={declineBooking} onStatus={setBookingStatus} />
      ) : bookings.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-zinc-400"><Calendar className="h-4 w-4" /> No bookings yet.</p>
      ) : (
        <ul className="divide-y divide-zinc-800">
          {bookings.map((b) => (
            <li key={b.id} className="flex items-center gap-3 py-2 text-sm">
              <div className="min-w-0 flex-1">
                <div className="truncate text-zinc-200">{b.customer_email || 'No email'} <span className="text-zinc-500">{money(b.quoted_price_cents)}</span></div>
                <div className="text-xs text-zinc-400">{new Date(b.starts_at).toLocaleString()}</div>
              </div>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[b.status]}`}>{b.status}</span>
              <select value={b.status} onChange={(e) => setBookingStatus(b, e.target.value)} className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100">
                {['pending', 'confirmed', 'cancelled', 'completed'].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
