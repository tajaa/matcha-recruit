import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { relativeTime, formatMoney, formatBytes, shortDate, shortDateWithYear } from './format'

const NOW = new Date('2026-07-20T12:00:00Z').getTime()
const ago = (ms: number) => new Date(NOW - ms).toISOString()

describe('relativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })
  afterEach(() => vi.useRealTimers())

  it('reads "just now" under a minute', () => {
    expect(relativeTime(ago(30_000))).toBe('just now')
  })

  it('counts minutes, then hours', () => {
    expect(relativeTime(ago(5 * 60_000))).toBe('5m ago')
    expect(relativeTime(ago(3 * 3_600_000))).toBe('3h ago')
  })

  it('rolls over to days past 24h', () => {
    // The FlagsTable copy never did this — it rendered "720h ago" at 30 days.
    expect(relativeTime(ago(6 * 86_400_000))).toBe('6d ago')
    expect(relativeTime(ago(30 * 3_600_000))).toBe('1d ago')
  })

  it('falls back to an absolute date past 30 days', () => {
    const out = relativeTime(ago(400 * 86_400_000))
    expect(out).not.toMatch(/ago/)
    expect(out).toMatch(/\d/)
  })

  it('clamps a future timestamp to "just now" rather than a negative count', () => {
    expect(relativeTime(new Date(NOW + 5_000).toISOString())).toBe('just now')
  })

  it('returns an em dash for null and unparseable input', () => {
    expect(relativeTime(null)).toBe('—')
    expect(relativeTime(undefined)).toBe('—')
    expect(relativeTime('not a date')).toBe('—')
  })
})

// Each option exists because a call site needed it, so each gets a test — the
// first version of this module flattened all of these into one output and
// silently changed four surfaces.
describe('relativeTime — per-surface options', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })
  afterEach(() => vi.useRealTimers())

  it('renders a custom empty string for null (inbox shows nothing, not an em dash)', () => {
    expect(relativeTime(null, { empty: '' })).toBe('')
  })

  it('honours a sentence-cased just-now label', () => {
    expect(relativeTime(ago(10_000), { justNowLabel: 'Just now' })).toBe('Just now')
  })

  it('uses the yesterday label at exactly one day, and only there', () => {
    expect(relativeTime(ago(25 * 3_600_000), { yesterdayLabel: 'Yesterday' })).toBe('Yesterday')
    expect(relativeTime(ago(49 * 3_600_000), { yesterdayLabel: 'Yesterday' })).toBe('2d ago')
  })

  it('omits the yesterday branch entirely when no label is given', () => {
    expect(relativeTime(ago(25 * 3_600_000))).toBe('1d ago')
  })

  it('switches to the absolute format at the configured cutoff', () => {
    // Blog comments: absolute after 7 days.
    const opts = { maxRelativeDays: 7, absolute: shortDateWithYear }
    expect(relativeTime(ago(6 * 86_400_000), opts)).toBe('6d ago')
    expect(relativeTime(ago(8 * 86_400_000), opts)).toMatch(/^[A-Z][a-z]{2} \d+, \d{4}$/)
  })

  it('counts days forever when maxRelativeDays is Infinity', () => {
    // Channel analytics compares channel ages; a date would be less useful.
    expect(relativeTime(ago(412 * 86_400_000), { maxRelativeDays: Infinity })).toBe('412d ago')
  })

  it('echoes the raw value on an unparseable date when onInvalid is given', () => {
    expect(relativeTime('garbage', { onInvalid: (raw) => String(raw) })).toBe('garbage')
  })

  it('inbox preset: 1d rolls straight to a bare date, never to "1d ago"', () => {
    const opts = { maxRelativeDays: 1, yesterdayLabel: 'Yesterday', absolute: shortDate }
    expect(relativeTime(ago(25 * 3_600_000), opts)).toBe('Yesterday')
    expect(relativeTime(ago(72 * 3_600_000), opts)).toMatch(/^[A-Z][a-z]{2} \d+$/)
  })
})

describe('formatMoney', () => {
  it('drops cents by default', () => {
    expect(formatMoney(1250)).toBe('$1,250')
    expect(formatMoney(1250.49)).toBe('$1,250')
  })

  it('keeps cents on request', () => {
    expect(formatMoney(1250.5, { cents: true })).toBe('$1,250.50')
  })

  it('formats zero as $0, not an em dash', () => {
    // The falsy-zero trap: `value || '—'` renders a real $0 balance as unknown.
    expect(formatMoney(0)).toBe('$0')
  })

  it('handles negatives and unset values', () => {
    expect(formatMoney(-400)).toBe('-$400')
    expect(formatMoney(null)).toBe('—')
    expect(formatMoney(undefined)).toBe('—')
  })
})

describe('formatBytes', () => {
  it('scales through the units', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB')
  })

  it('formats zero bytes rather than an em dash', () => {
    expect(formatBytes(0)).toBe('0 B')
  })

  it('returns an em dash when unset', () => {
    expect(formatBytes(null)).toBe('—')
  })
})
