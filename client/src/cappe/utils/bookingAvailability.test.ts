import { describe, expect, it } from 'vitest'
import type { CappeAvailabilitySlot, CappeBookingType } from '../types'
import { applicableSlotsForType, slotAppliesToType, unavailableStaffWindowIndexes } from './bookingAvailability'

const sharedType: CappeBookingType = {
  id: 'consultation', site_id: 'site', name: 'Consultation', description: null,
  duration_minutes: 30, price_cents: 0, status: 'active', requires_approval: false,
  pricing_mode: 'flat', category: null, buffer_minutes: 0, staff_ids: [], created_at: '', updated_at: '',
}
const lauraType: CappeBookingType = { ...sharedType, id: 'cake-consultation', staff_ids: ['laura'] }
const sharedWindow: CappeAvailabilitySlot = {
  weekday: 1, start_time: '11:00', end_time: '19:00', booking_type_id: null, staff_id: null,
}
const lauraWindow: CappeAvailabilitySlot = { ...sharedWindow, staff_id: 'laura' }

describe('slotAppliesToType', () => {
  it('allows shared windows for every matching appointment type', () => {
    expect(slotAppliesToType(sharedWindow, sharedType)).toBe(true)
    expect(slotAppliesToType(sharedWindow, lauraType)).toBe(true)
  })

  it('does not expose staff-only windows to a shared-calendar type', () => {
    expect(slotAppliesToType(lauraWindow, sharedType)).toBe(false)
  })

  it('exposes staff-only windows only to types performed by that staff member', () => {
    expect(slotAppliesToType(lauraWindow, lauraType)).toBe(true)
    expect(slotAppliesToType(lauraWindow, { ...lauraType, staff_ids: ['sam'] })).toBe(false)
  })

  it('respects booking-type-specific windows', () => {
    expect(slotAppliesToType({ ...sharedWindow, booking_type_id: 'other' }, lauraType)).toBe(false)
  })
})

describe('booking availability diagnostics', () => {
  it('filters the calendar to windows a type can actually book', () => {
    expect(applicableSlotsForType([sharedWindow, lauraWindow], sharedType)).toEqual([sharedWindow])
    expect(applicableSlotsForType([sharedWindow, lauraWindow], lauraType)).toEqual([sharedWindow, lauraWindow])
  })

  it('flags staff windows that no active appointment type can use', () => {
    expect(unavailableStaffWindowIndexes([lauraWindow], [sharedType])).toEqual(new Set([0]))
    expect(unavailableStaffWindowIndexes([lauraWindow], [lauraType])).toEqual(new Set())
    expect(unavailableStaffWindowIndexes([lauraWindow], [{ ...sharedType, status: 'archived', staff_ids: ['laura'] }])).toEqual(new Set([0]))
  })
})
