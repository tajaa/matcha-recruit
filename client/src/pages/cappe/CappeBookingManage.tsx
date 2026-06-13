import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Calendar, CheckCircle2, XCircle, ArrowLeft } from 'lucide-react'
import { cappePublicGet, cappePublicPost } from '../../api/cappeClient'
import type { CappePublicBooking, CappeSlot, CappeSlotsResponse } from '../../types/cappe'

function money(cents: number | null): string {
  if (!cents) return ''
  return `$${(cents / 100).toFixed(2)}`
}
function whenLong(ts: string): string {
  return new Date(ts).toLocaleString([], {
    weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

// Public, token-gated page where a customer views / cancels / reschedules their
// booking from an emailed link. No account required.
export default function CappeBookingManage() {
  const { token } = useParams<{ token: string }>()
  const [booking, setBooking] = useState<CappePublicBooking | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [rescheduling, setRescheduling] = useState(false)
  const [slots, setSlots] = useState<CappeSlot[] | null>(null)
  const [slotsTz, setSlotsTz] = useState('')

  useEffect(() => {
    cappePublicGet<CappePublicBooking>(`/public/bookings/${token}`)
      .then(setBooking)
      .catch((e) => setError(e instanceof Error ? e.message : 'Booking not found'))
  }, [token])

  async function cancel() {
    if (!booking || !confirm('Cancel this booking? This frees the time slot.')) return
    setBusy(true)
    setError(null)
    try {
      const updated = await cappePublicPost<CappePublicBooking>(`/public/bookings/${token}/cancel`, {})
      setBooking(updated)
      setNotice('Your booking was cancelled.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not cancel')
    } finally {
      setBusy(false)
    }
  }

  async function openReschedule() {
    if (!booking?.booking_type_id) return
    setRescheduling(true)
    setError(null)
    setSlots(null)
    try {
      const res = await cappePublicGet<CappeSlotsResponse>(
        `/public/sites/${booking.slug}/booking-types/${booking.booking_type_id}/slots`,
      )
      setSlots(res.slots)
      setSlotsTz(res.timezone)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load times')
    }
  }

  async function pickSlot(s: CappeSlot) {
    if (!booking) return
    setBusy(true)
    setError(null)
    try {
      const updated = await cappePublicPost<CappePublicBooking>(`/public/bookings/${token}/reschedule`, {
        starts_at: s.start,
        ends_at: s.end,
      })
      setBooking(updated)
      setRescheduling(false)
      setNotice('Your booking was moved.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not reschedule')
    } finally {
      setBusy(false)
    }
  }

  if (error && !booking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
        <p className="text-sm text-zinc-400">{error}</p>
      </div>
    )
  }
  if (!booking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-600" />
      </div>
    )
  }

  const cancelled = booking.status === 'cancelled' || booking.status === 'declined'
  const statusLabel: Record<string, string> = {
    pending: 'Pending approval', confirmed: 'Confirmed', completed: 'Completed',
    cancelled: 'Cancelled', declined: 'Declined',
  }

  // Group reschedule slots by day for a compact picker.
  const byDay: { label: string; items: CappeSlot[] }[] = []
  if (slots) {
    const map = new Map<string, CappeSlot[]>()
    for (const s of slots) {
      if (!map.has(s.date)) { map.set(s.date, []); byDay.push({ label: s.day_label, items: map.get(s.date)! }) }
      map.get(s.date)!.push(s)
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col bg-zinc-950 px-4 py-10 text-zinc-100">
      <header className="mb-6">
        <div className="text-xs uppercase tracking-wide text-lime-400">{booking.site_name}</div>
        <h1 className="mt-1 text-xl font-semibold text-zinc-50">Your booking</h1>
      </header>

      {notice && <p className="mb-4 rounded-lg bg-lime-400/10 px-4 py-2 text-sm text-lime-300">{notice}</p>}
      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-zinc-50">{booking.type_name}</div>
            <div className="mt-1 flex items-center gap-1.5 text-sm text-zinc-400">
              <Calendar className="h-4 w-4" /> {whenLong(booking.starts_at)}
            </div>
            <div className="mt-1 text-xs text-zinc-500">Times shown in {booking.timezone}</div>
          </div>
          <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${
            cancelled ? 'bg-zinc-800 text-zinc-400' : 'bg-lime-400/15 text-lime-300'
          }`}>
            {statusLabel[booking.status] || booking.status}
          </span>
        </div>
        {booking.quoted_price_cents ? (
          <div className="mt-4 border-t border-zinc-800 pt-3 text-sm text-zinc-300">
            Price: <span className="font-semibold text-zinc-100">{money(booking.quoted_price_cents)}</span>
          </div>
        ) : null}
      </div>

      {booking.can_modify && !rescheduling && (
        <div className="mt-4 flex gap-2">
          <button
            onClick={openReschedule}
            disabled={busy}
            className="flex items-center gap-1.5 rounded-lg bg-lime-400 px-4 py-2.5 text-sm font-semibold text-zinc-950 hover:bg-lime-300 disabled:opacity-60"
          >
            <Calendar className="h-4 w-4" /> Reschedule
          </button>
          <button
            onClick={cancel}
            disabled={busy}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-4 py-2.5 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60"
          >
            <XCircle className="h-4 w-4" /> Cancel
          </button>
        </div>
      )}

      {cancelled && (
        <p className="mt-4 flex items-center gap-1.5 text-sm text-zinc-500">
          <XCircle className="h-4 w-4" /> This booking is {statusLabel[booking.status]?.toLowerCase() || booking.status}.
        </p>
      )}
      {!booking.can_modify && !cancelled && (
        <p className="mt-4 flex items-center gap-1.5 text-sm text-zinc-500">
          <CheckCircle2 className="h-4 w-4" /> This booking can no longer be changed online.
        </p>
      )}

      {rescheduling && (
        <div className="mt-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
          <button onClick={() => setRescheduling(false)} className="mb-3 flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300">
            <ArrowLeft className="h-3.5 w-3.5" /> Back
          </button>
          <h2 className="mb-3 text-sm font-semibold text-zinc-100">Pick a new time</h2>
          {slots === null ? (
            <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin text-zinc-600" /></div>
          ) : slots.length === 0 ? (
            <p className="py-4 text-sm text-zinc-500">No open times in the next few weeks.</p>
          ) : (
            <>
              <p className="mb-3 text-xs text-zinc-500">Times in {slotsTz}</p>
              <div className="space-y-4">
                {byDay.map((d) => (
                  <div key={d.label}>
                    <div className="mb-1.5 text-xs font-medium text-zinc-400">{d.label}</div>
                    <div className="flex flex-wrap gap-2">
                      {d.items.map((s) => (
                        <button
                          key={s.start}
                          onClick={() => pickSlot(s)}
                          disabled={busy}
                          className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 hover:border-lime-500 hover:text-lime-300 disabled:opacity-60"
                        >
                          {s.time_label}{s.price_cents ? ` · ${money(s.price_cents)}` : ''}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
