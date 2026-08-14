import { describe, expect, it } from 'vitest'
import { bookingDateKey, formatBookingDateTime, formatBookingTime } from './bookingTime'

describe('booking time formatting', () => {
  it('formats an instant in the booking timezone', () => {
    const instant = '2026-08-20T16:00:00Z'

    expect(formatBookingTime(instant, 'America/New_York', 'en-US')).toBe('12:00 PM')
    expect(formatBookingDateTime(instant, 'America/New_York', 'en-US')).toBe('Thu, Aug 20, 12:00 PM')
  })

  it('uses the booking timezone for the calendar date near midnight', () => {
    expect(bookingDateKey('2026-08-20T02:00:00Z', 'America/Los_Angeles')).toBe('2026-08-19')
  })

  it('falls back to UTC for missing or invalid timezones', () => {
    const instant = '2026-08-20T16:00:00Z'

    expect(bookingDateKey(instant, undefined)).toBe('2026-08-20')
    expect(formatBookingTime(instant, 'Not/AZone', 'en-US')).toBe('4:00 PM')
  })
})
