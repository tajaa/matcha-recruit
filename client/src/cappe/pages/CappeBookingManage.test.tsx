import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CappeBookingManage from './CappeBookingManage'
import type { CappePublicBooking } from '../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api', () => ({ cappePublicGet: api.get, cappePublicPost: api.post }))

function booking(over: Partial<CappePublicBooking> = {}): CappePublicBooking {
  return {
    status: 'confirmed', type_name: 'Cut', site_name: 'Salon', slug: 'salon', booking_type_id: 't-1',
    starts_at: '2026-10-20T16:00:00Z', ends_at: '2026-10-20T17:00:00Z', quoted_price_cents: 5000,
    timezone: 'America/New_York', can_modify: true, staff_id: 'st-1', staff_name: 'Ben',
    location_id: 'loc-1', location_name: 'Mission', ...over,
  }
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/cappe/booking/tok']}>
      <Routes><Route path="/cappe/booking/:token" element={<CappeBookingManage />} /></Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
})

describe('CappeBookingManage', () => {
  it('says who and where, and asks for that stylist’s times at that location', async () => {
    api.get.mockResolvedValueOnce(booking()).mockResolvedValueOnce({ timezone: 'America/New_York', discount_percent: 0, slots: [] })
    renderPage()
    expect(await screen.findByText('With Ben at Mission')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Reschedule/ }))
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith(
      '/public/sites/salon/booking-types/t-1/slots?staff_id=st-1&location_id=loc-1',
    ))
    expect(await screen.findByText(/No open times in the next few weeks with Ben/)).toBeInTheDocument()
  })

  it('says when a moved booking needs approval again', async () => {
    const slot = { start: '2026-10-21T10:00:00', end: '2026-10-21T11:00:00', date: '2026-10-21', day_label: 'Wed Oct 21', time_label: '10:00 AM', price_cents: 5000 }
    api.get.mockResolvedValueOnce(booking()).mockResolvedValueOnce({ timezone: 'America/New_York', discount_percent: 0, slots: [slot] })
    api.post.mockResolvedValueOnce(booking({ status: 'pending' }))
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /Reschedule/ }))
    fireEvent.click(await screen.findByRole('button', { name: /10:00 AM/ }))
    expect(await screen.findByText(/needs the host’s approval/)).toBeInTheDocument()
  })

  it('offers no dead Reschedule button when the service is gone', async () => {
    api.get.mockResolvedValueOnce(booking({ booking_type_id: null }))
    renderPage()
    expect(await screen.findByText(/no longer booked online/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Reschedule/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Cancel/ })).toBeInTheDocument()
  })
})
