import type { Dispatch, SetStateAction } from 'react'
import { AlertTriangle, Calendar, List } from 'lucide-react'
import BookingsCalendar from '../../../components/BookingsCalendar'
import type { CappeBooking, CappeBookingType, CappeAvailabilitySlot, CappeStaff } from '../../../types'
import { formatBookingDateTime } from '../../../utils/bookingTime'
import { BOOKING_ACTION_LABEL, NEXT_BOOKING_STATUSES, bookingIsPaid } from '../../../utils/bookingStatus'
import { money, statusStyle } from './constants'

interface ScheduleSectionProps {
  view: 'calendar' | 'list'
  setView: Dispatch<SetStateAction<'calendar' | 'list'>>
  bookings: CappeBooking[]
  slots: CappeAvailabilitySlot[]
  types: CappeBookingType[]
  staff: CappeStaff[]
  acceptBooking: (b: CappeBooking) => void
  declineBooking: (b: CappeBooking) => void
  setBookingStatus: (b: CappeBooking, status: string) => void
  calendarTimezone: string
  timezoneForBooking: (booking: CappeBooking) => string
  allLocations: boolean
}

export function ScheduleSection({
  view, setView, bookings, slots, types, staff, acceptBooking, declineBooking, setBookingStatus,
  calendarTimezone, timezoneForBooking, allLocations,
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
        <BookingsCalendar
          bookings={bookings}
          availability={slots}
          types={types}
          staff={staff}
          onAccept={acceptBooking}
          onDecline={declineBooking}
          onStatus={setBookingStatus}
          calendarTimezone={calendarTimezone}
          timezoneForBooking={timezoneForBooking}
          allLocations={allLocations}
        />
      ) : bookings.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-zinc-400"><Calendar className="h-4 w-4" /> No bookings yet.</p>
      ) : (
        <ul className="divide-y divide-zinc-800">
          {bookings.map((b) => {
            const next = NEXT_BOOKING_STATUSES[b.status] || []
            const type = types.find((t) => t.id === b.booking_type_id)
            return (
            <li key={b.id} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 py-2 text-sm">
              <div className="min-w-0 flex-1 basis-56">
                <div className="truncate text-zinc-200">
                  {b.customer_name || b.customer_email || 'No email'}
                  {b.customer_name && b.customer_email && <span className="ml-1.5 text-zinc-500">{b.customer_email}</span>}
                </div>
                <div className="text-xs text-zinc-400">
                  {formatBookingDateTime(b.starts_at, b.timezone || timezoneForBooking(b))}
                  {type && ` · ${type.name}`}
                  {b.staff_name && ` · with ${b.staff_name}`}
                  {allLocations && b.location_name && ` · ${b.location_name}`}
                  {' · '}{money(b.quoted_price_cents)}
                </div>
                {bookingIsPaid(b) && (b.status === 'cancelled' || b.status === 'declined') && (
                  <div className="mt-0.5 flex items-center gap-1 text-xs text-amber-400">
                    <AlertTriangle className="h-3 w-3" /> Paid in your shop and not refunded — refund it from Orders if your policy allows.
                  </div>
                )}
              </div>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[b.status]}`}>{b.status}</span>
              {b.status === 'pending' && b.requires_approval ? (
                <>
                  <button onClick={() => acceptBooking(b)} className="rounded-lg bg-emerald-500 px-2.5 py-1 text-xs font-semibold text-zinc-950 hover:bg-emerald-400">Accept</button>
                  <button onClick={() => declineBooking(b)} className="rounded-lg border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800">Decline</button>
                </>
              ) : next.length > 0 && (
                <select
                  value=""
                  aria-label={`Change booking for ${b.customer_name || b.customer_email || 'customer'}`}
                  onChange={(e) => setBookingStatus(b, e.target.value)}
                  className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100"
                >
                  <option value="">Change…</option>
                  {next.map((s) => <option key={s} value={s}>{BOOKING_ACTION_LABEL[s] || s}</option>)}
                </select>
              )}
            </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
