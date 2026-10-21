import { describe, expect, it } from 'vitest'
import {
  localInputToIso, nextSlot, normalizeHashtags, scheduleError, spreadTimes, toLocalInput, withHashtags,
} from './socialSchedule'

describe('datetime-local round trip', () => {
  it('reads and writes local time', () => {
    const d = new Date(2026, 9, 21, 9, 5)
    expect(toLocalInput(d)).toBe('2026-10-21T09:05')
    expect(localInputToIso('2026-10-21T09:05')).toBe(d.toISOString())
  })

  it('is null for nothing or nonsense', () => {
    expect(localInputToIso('')).toBeNull()
    expect(localInputToIso('not a date')).toBeNull()
  })
})

describe('scheduleError', () => {
  it('wants a real time in the future', () => {
    const now = new Date(2026, 9, 21, 9, 0)
    expect(scheduleError('', now)).toBe('Pick a time')
    expect(scheduleError('2026-10-21T08:59', now)).toBe('Pick a time in the future')
    expect(scheduleError('2026-10-21T09:30', now)).toBeNull()
  })
})

describe('nextSlot', () => {
  it('is the next whole hour at least 15 minutes out', () => {
    expect(nextSlot(new Date(2026, 9, 21, 9, 50))).toEqual(new Date(2026, 9, 21, 11, 0))
    expect(nextSlot(new Date(2026, 9, 21, 9, 10))).toEqual(new Date(2026, 9, 21, 10, 0))
    expect(nextSlot(new Date(2026, 9, 21, 9, 45))).toEqual(new Date(2026, 9, 21, 10, 0))
  })
})

describe('spreadTimes', () => {
  it('keeps the wall-clock time, days apart', () => {
    const start = new Date(2026, 9, 30, 9, 0)
    const times = spreadTimes(start, 3, 2)
    expect(times.map((t) => [t.getDate(), t.getHours()])).toEqual([[30, 9], [1, 9], [3, 9]])
  })

  it('treats a zero interval as daily and a zero count as nothing', () => {
    expect(spreadTimes(new Date(2026, 0, 1, 8), 2, 0).map((t) => t.getDate())).toEqual([1, 2])
    expect(spreadTimes(new Date(), 0, 1)).toEqual([])
  })
})

describe('hashtags', () => {
  it('normalizes and de-duplicates', () => {
    expect(normalizeHashtags('#Coffee, coffee  cold-brew #')).toEqual(['#coffee', '#coldbrew'])
    expect(normalizeHashtags(['#Café', 'latte'])).toEqual(['#café', '#latte'])
  })

  it('appends only what the caption lacks', () => {
    expect(withHashtags('New roast #coffee', ['#coffee', '#beans'])).toBe('New roast #coffee\n\n#beans')
    expect(withHashtags('All set #coffee', ['coffee'])).toBe('All set #coffee')
    expect(withHashtags('', ['a'])).toBe('#a')
  })
})
