import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { relativeTime, formatMoney, formatBytes } from './format'

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
