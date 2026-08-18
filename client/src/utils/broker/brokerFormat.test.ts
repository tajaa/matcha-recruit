import { describe, it, expect } from 'vitest'
import { daysUntilDate, renewalBand, compareRenewal } from './brokerFormat'

describe('daysUntilDate', () => {
  const today = new Date(2026, 7, 18) // 2026-08-18, local midnight

  it('null / undefined / empty', () => {
    expect(daysUntilDate(null, today)).toBeNull()
    expect(daysUntilDate(undefined, today)).toBeNull()
    expect(daysUntilDate('', today)).toBeNull()
  })

  it('garbage input', () => {
    expect(daysUntilDate('not-a-date', today)).toBeNull()
  })

  it('same day is 0', () => {
    expect(daysUntilDate('2026-08-18', today)).toBe(0)
  })

  it('one day forward / back', () => {
    expect(daysUntilDate('2026-08-19', today)).toBe(1)
    expect(daysUntilDate('2026-08-17', today)).toBe(-1)
  })

  it('90 days out', () => {
    expect(daysUntilDate('2026-11-16', today)).toBe(90)
  })

  it('is unaffected by a late time-of-day on `today`', () => {
    const lateToday = new Date(2026, 7, 18, 23, 59, 59)
    expect(daysUntilDate('2026-08-18', lateToday)).toBe(0)
  })

  it('handles a DST-crossing span without drifting off by a day', () => {
    // 2026-03-08 is the US spring-forward date.
    expect(daysUntilDate('2026-03-15', new Date(2026, 2, 1))).toBe(14)
  })

  it('takes the date part of a full ISO datetime', () => {
    expect(daysUntilDate('2026-08-18T00:00:00Z', today)).toBe(0)
  })
})

describe('renewalBand', () => {
  it('boundaries', () => {
    expect(renewalBand(null)).toBe('unknown')
    expect(renewalBand(-1)).toBe('expired')
    expect(renewalBand(0)).toBe('critical')
    expect(renewalBand(59)).toBe('critical')
    expect(renewalBand(60)).toBe('warning')
    expect(renewalBand(90)).toBe('warning')
    expect(renewalBand(91)).toBe('normal')
  })
})

describe('compareRenewal', () => {
  it('earlier date sorts first ascending', () => {
    expect(compareRenewal('2026-01-01', '2026-06-01', 'asc')).toBeLessThan(0)
  })

  it('reverses on desc', () => {
    expect(compareRenewal('2026-01-01', '2026-06-01', 'desc')).toBeGreaterThan(0)
  })

  it('null sorts last on both directions', () => {
    expect(compareRenewal(null, '2026-06-01', 'asc')).toBeGreaterThan(0)
    expect(compareRenewal(null, '2026-06-01', 'desc')).toBeGreaterThan(0)
    expect(compareRenewal('2026-06-01', null, 'asc')).toBeLessThan(0)
    expect(compareRenewal('2026-06-01', null, 'desc')).toBeLessThan(0)
  })

  it('both null is a tie', () => {
    expect(compareRenewal(null, null, 'asc')).toBe(0)
  })
})
