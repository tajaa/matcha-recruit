import type { CappeBooking } from '../types'

/** What an owner may move a booking to by hand. Mirrors the server's
 *  `booking_lifecycle.ALLOWED_TRANSITIONS` — the server is the authority and
 *  refuses anything else with a reason; this keeps impossible choices out of
 *  the menu. Declining has its own action (it carries a reason). A cancelled
 *  or declined booking is never reopened: its time may have been booked since. */
export const NEXT_BOOKING_STATUSES: Record<string, CappeBooking['status'][]> = {
  pending: ['confirmed', 'cancelled'],
  confirmed: ['cancelled', 'completed'],
}

export const BOOKING_ACTION_LABEL: Record<string, string> = {
  confirmed: 'Confirm',
  cancelled: 'Cancel booking',
  completed: 'Mark completed',
}

/** The booking was bought through the shop and the money is still held. */
export function bookingIsPaid(b: Pick<CappeBooking, 'order_id' | 'order_status'>): boolean {
  return Boolean(b.order_id) && (b.order_status === 'paid' || b.order_status === 'fulfilled')
}

/** The question to ask before a status change, or null when none is needed. */
export function bookingStatusQuestion(b: CappeBooking, next: string): string | null {
  if (next !== 'cancelled') return null
  const who = b.customer_name || b.customer_email || 'the customer'
  const base = `Cancel this booking? The time is freed and ${who} is emailed that you cancelled.`
  return bookingIsPaid(b)
    ? `${base}\n\nIt was paid for in your shop. Cancelling does not refund it — refund the order from Orders if your policy allows.`
    : base
}
