import { describe, expect, it } from 'vitest'
import { NEXT_BOOKING_STATUSES, bookingIsPaid, bookingStatusQuestion } from './bookingStatus'
import type { CappeBooking } from '../types'

const booking = (over: Partial<CappeBooking> = {}) => ({
  customer_name: 'Ana', customer_email: 'ana@example.com', order_id: null, order_status: null, ...over,
}) as CappeBooking

describe('booking status rules (mirror of booking_lifecycle.ALLOWED_TRANSITIONS)', () => {
  it('never offers a way back to a released slot', () => {
    for (const released of ['cancelled', 'declined', 'completed']) {
      expect(NEXT_BOOKING_STATUSES[released]).toBeUndefined()
    }
    expect(NEXT_BOOKING_STATUSES.pending).toEqual(['confirmed', 'cancelled'])
    expect(NEXT_BOOKING_STATUSES.confirmed).toEqual(['cancelled', 'completed'])
  })

  it('knows when a booking’s money is still held', () => {
    expect(bookingIsPaid(booking({ order_id: 'o-1', order_status: 'paid' }))).toBe(true)
    expect(bookingIsPaid(booking({ order_id: 'o-1', order_status: 'pending' }))).toBe(false)
    expect(bookingIsPaid(booking())).toBe(false)
  })

  it('asks before cancelling, and warns that a paid booking is not refunded', () => {
    expect(bookingStatusQuestion(booking(), 'completed')).toBeNull()
    expect(bookingStatusQuestion(booking(), 'cancelled')).toContain('Ana is emailed')
    expect(bookingStatusQuestion(booking(), 'cancelled')).not.toContain('refund')
    expect(bookingStatusQuestion(booking({ order_id: 'o-1', order_status: 'paid' }), 'cancelled'))
      .toContain('does not refund it')
  })
})
