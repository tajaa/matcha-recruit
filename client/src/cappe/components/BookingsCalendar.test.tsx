import { render, screen, fireEvent } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import BookingsCalendar from './BookingsCalendar'
import type { CappeBooking } from '../types'

const booking: CappeBooking = {
  id: 'booking-1',
  site_id: 'site-1',
  booking_type_id: null,
  location_id: 'location-la',
  location_name: 'Los Angeles',
  customer_name: 'Customer',
  customer_email: 'customer@example.com',
  starts_at: '2026-08-20T16:00:00Z',
  ends_at: '2026-08-20T16:30:00Z',
  status: 'confirmed',
  note: null,
  requires_approval: false,
  quoted_price_cents: null,
  approved_at: null,
  decline_reason: null,
  rider_acknowledged: false,
  rider_snapshot: [],
  created_at: '2026-08-01T00:00:00Z',
}

describe('BookingsCalendar timezone display', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-13T12:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('groups and displays each booking in its location timezone', () => {
    render(
      <BookingsCalendar
        bookings={[booking]}
        availability={[]}
        types={[]}
        staff={[]}
        onAccept={vi.fn()}
        onDecline={vi.fn()}
        onStatus={vi.fn()}
        calendarTimezone="America/New_York"
        timezoneForBooking={() => 'America/Los_Angeles'}
        allLocations
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /^20/ }))

    expect(screen.getAllByText('9:00 AM').length).toBeGreaterThan(0)
    expect(screen.getByText(/Los Angeles/)).toBeTruthy()
  })
})
