import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NewBookingForm } from './NewBookingForm'
import { ScheduleSection } from './ScheduleSection'
import { TimeOffSection } from './TimeOffSection'
import { localInputValue } from '../../../utils/bookingTime'
import type { CappeBooking, CappeBookingType, CappeStaff, CappeTimeOff } from '../../../types'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('../../../api', () => ({ cappeApi: api }))
vi.mock('../../../components/BookingsCalendar', () => ({ default: () => null }))

const TYPE = { id: 't-1', name: 'Cut', status: 'active', pricing_mode: 'flat', staff_ids: ['s-1'], location_id: null } as unknown as CappeBookingType
const STAFF = [{ id: 's-1', name: 'Ben', active: true }] as unknown as CappeStaff[]
const BOOKING = {
  id: 'b-1', site_id: 'site', booking_type_id: 't-1', customer_name: 'Ana', customer_email: 'ana@example.com',
  starts_at: '2026-10-20T16:00:00Z', ends_at: '2026-10-20T17:00:00Z', status: 'confirmed', note: null,
  requires_approval: false, quoted_price_cents: 5000, approved_at: null, decline_reason: null,
  rider_acknowledged: false, rider_snapshot: [], created_at: '2026-10-01T00:00:00Z', timezone: 'America/New_York',
} as CappeBooking

beforeEach(() => {
  api.get.mockReset(); api.post.mockReset(); api.put.mockReset(); api.delete.mockReset()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

describe('booking someone in', () => {
  it('books the chosen service, person and time, and emails them', async () => {
    const onBooked = vi.fn()
    api.post.mockResolvedValue({ ...BOOKING, id: 'b-2' })
    render(<NewBookingForm siteId="site" types={[TYPE]} staff={STAFF} locations={[]} defaultLocation="" onBooked={onBooked} onCancel={() => {}} />)
    fireEvent.change(screen.getByLabelText('With'), { target: { value: 's-1' } })
    fireEvent.change(screen.getByLabelText('Starts'), { target: { value: '2026-10-21T09:30' } })
    fireEvent.change(screen.getByLabelText('Customer name'), { target: { value: ' Ana ' } })
    fireEvent.change(screen.getByLabelText('Email (optional)'), { target: { value: 'ana@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Book it' }))
    await waitFor(() => expect(onBooked).toHaveBeenCalled())
    expect(api.post).toHaveBeenCalledWith('/sites/site/bookings', expect.objectContaining({
      booking_type_id: 't-1', starts_at: '2026-10-21T09:30', staff_id: 's-1', customer_name: 'Ana',
      customer_email: 'ana@example.com', notify: true,
    }))
  })

  it('asks for who will see them when the service is staffed', () => {
    render(<NewBookingForm siteId="site" types={[TYPE]} staff={STAFF} locations={[]} defaultLocation="" onBooked={() => {}} onCancel={() => {}} />)
    fireEvent.change(screen.getByLabelText('Starts'), { target: { value: '2026-10-21T09:30' } })
    fireEvent.change(screen.getByLabelText('Customer name'), { target: { value: 'Ana' } })
    fireEvent.click(screen.getByRole('button', { name: 'Book it' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Choose who will see them')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('shows why the server refused it', async () => {
    api.post.mockRejectedValue(new Error('That slot is taken'))
    render(<NewBookingForm siteId="site" types={[{ ...TYPE, staff_ids: [] }]} staff={[]} locations={[]} defaultLocation="" onBooked={() => {}} onCancel={() => {}} />)
    fireEvent.change(screen.getByLabelText('Starts'), { target: { value: '2026-10-21T09:30' } })
    fireEvent.change(screen.getByLabelText('Customer name'), { target: { value: 'Walk-in' } })
    fireEvent.click(screen.getByRole('button', { name: 'Book it' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('That slot is taken')
  })
})

describe('moving a booking', () => {
  it('moves it to a new time in its own timezone', async () => {
    const upsert = vi.fn()
    api.put.mockResolvedValue({ ...BOOKING, starts_at: '2026-10-21T14:00:00Z' })
    render(<ScheduleSection view="list" setView={() => {}} bookings={[BOOKING]} slots={[]} types={[TYPE]} staff={STAFF}
      acceptBooking={() => {}} declineBooking={() => {}} setBookingStatus={() => {}} calendarTimezone="UTC"
      timezoneForBooking={() => 'UTC'} allLocations={false} siteId="site" upsertBooking={upsert} />)
    fireEvent.click(screen.getByRole('button', { name: 'Move' }))
    const input = screen.getByLabelText('New time')
    expect(input).toHaveValue('2026-10-20T12:00')                 // 16:00 UTC in New York
    fireEvent.change(input, { target: { value: '2026-10-21T10:00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Move' }))
    await waitFor(() => expect(upsert).toHaveBeenCalled())
    expect(api.put).toHaveBeenCalledWith('/sites/site/bookings/b-1/time', { starts_at: '2026-10-21T10:00', notify: true })
  })

  it('offers booking someone in', () => {
    render(<ScheduleSection view="list" setView={() => {}} bookings={[]} slots={[]} types={[TYPE]} staff={STAFF}
      acceptBooking={() => {}} declineBooking={() => {}} setBookingStatus={() => {}} calendarTimezone="UTC"
      timezoneForBooking={() => 'UTC'} allLocations={false} siteId="site" upsertBooking={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Book someone in/ }))
    expect(screen.getByRole('form', { name: 'Book someone in' })).toBeInTheDocument()
  })
})

describe('time off', () => {
  const ROW: CappeTimeOff = {
    id: 'to-1', staff_id: null, staff_name: null, location_id: null, location_name: null,
    starts_at: '2026-12-24T00:00:00Z', ends_at: '2026-12-27T00:00:00Z', reason: 'Holiday', created_at: '2026-10-01T00:00:00Z',
  }

  it('lists, adds and removes time off', async () => {
    api.get.mockResolvedValue([ROW])
    render(<TimeOffSection siteId="site" staff={STAFF} locations={[]} timezone="UTC" />)
    expect(await screen.findByText(/Everyone · Holiday/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Who'), { target: { value: 's-1' } })
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-11-02T00:00' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-11-03T00:00' } })
    api.post.mockResolvedValue({ ...ROW, id: 'to-2', staff_id: 's-1', staff_name: 'Ben', reason: null, starts_at: '2026-11-02T00:00:00Z' })
    fireEvent.click(screen.getByRole('button', { name: 'Add time off' }))
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/sites/site/time-off', {
      starts_at: '2026-11-02T00:00', ends_at: '2026-11-03T00:00', staff_id: 's-1', location_id: null, reason: null,
    }))
    expect(await screen.findByText(/^Ben$/, { selector: 'span span' })).toBeInTheDocument()
    api.delete.mockResolvedValue(undefined)
    fireEvent.click(screen.getAllByRole('button', { name: 'Remove time off' })[1])
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/sites/site/time-off/to-1'))
  })

  it('refuses an end before the start', async () => {
    api.get.mockResolvedValue([])
    render(<TimeOffSection siteId="site" staff={STAFF} locations={[]} timezone="UTC" />)
    await screen.findByText('No time off coming up.')
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-11-03T00:00' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-11-02T00:00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add time off' }))
    expect(screen.getByRole('alert')).toHaveTextContent('The end must be after the start')
    expect(api.post).not.toHaveBeenCalled()
  })
})

describe('localInputValue', () => {
  it('writes a timestamp as a local datetime input in a timezone', () => {
    expect(localInputValue('2026-10-20T16:00:00Z', 'America/New_York')).toBe('2026-10-20T12:00')
    expect(localInputValue('2026-10-20T16:00:00Z', 'Nowhere/Invalid')).toBe('2026-10-20T16:00')
  })
})
