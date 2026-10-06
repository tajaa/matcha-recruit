import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ScheduleSection } from './ScheduleSection'
import type { CappeBooking } from '../../../types'

vi.mock('../../../components/BookingsCalendar', () => ({ default: () => null }))

function booking(over: Partial<CappeBooking>): CappeBooking {
  return {
    id: 'b-1', site_id: 's-1', booking_type_id: 't-1', customer_name: 'Ana', customer_email: 'ana@example.com',
    starts_at: '2026-10-20T16:00:00Z', ends_at: '2026-10-20T17:00:00Z', status: 'confirmed', note: null,
    requires_approval: false, quoted_price_cents: 5000, approved_at: null, decline_reason: null,
    rider_acknowledged: false, rider_snapshot: [], created_at: '2026-10-01T00:00:00Z',
    staff_name: 'Ben', timezone: 'America/New_York', ...over,
  }
}

function renderList(bookings: CappeBooking[]) {
  const handlers = { accept: vi.fn(), decline: vi.fn(), status: vi.fn() }
  render(
    <ScheduleSection
      view="list" setView={() => {}} bookings={bookings} slots={[]}
      types={[{ id: 't-1', name: 'Cut' } as never]} staff={[]}
      acceptBooking={handlers.accept} declineBooking={handlers.decline} setBookingStatus={handlers.status}
      calendarTimezone="UTC" timezoneForBooking={() => 'UTC'} allLocations={false}
    />,
  )
  return handlers
}

describe('ScheduleSection — the list', () => {
  it('names the customer, the service and the stylist, in the booking’s timezone', () => {
    renderList([booking({})])
    expect(screen.getByText('Ana')).toBeInTheDocument()
    expect(screen.getByText(/Cut · with Ben · \$50\.00/)).toBeInTheDocument()
    expect(screen.getByText(/12:00 PM/)).toBeInTheDocument()   // 16:00 UTC in New York
  })

  it('offers only the moves the server allows', () => {
    const h = renderList([booking({ status: 'confirmed' })])
    const menu = screen.getByRole('combobox', { name: /Change booking for Ana/ })
    expect(within(menu).getAllByRole('option').map((o) => o.textContent)).toEqual(['Change…', 'Cancel booking', 'Mark completed'])
    fireEvent.change(menu, { target: { value: 'completed' } })
    expect(h.status).toHaveBeenCalledWith(expect.objectContaining({ id: 'b-1' }), 'completed')
  })

  it('offers nothing on a cancelled booking — its time may be taken', () => {
    renderList([booking({ status: 'cancelled' })])
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('turns a request into Accept / Decline', () => {
    const h = renderList([booking({ status: 'pending', requires_approval: true })])
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }))
    fireEvent.click(screen.getByRole('button', { name: 'Decline' }))
    expect(h.accept).toHaveBeenCalled()
    expect(h.decline).toHaveBeenCalled()
  })

  it('flags a cancelled booking whose shop payment was never refunded', () => {
    renderList([booking({ status: 'cancelled', order_id: 'o-1', order_status: 'paid' })])
    expect(screen.getByText(/Paid in your shop and not refunded/)).toBeInTheDocument()
  })
})
