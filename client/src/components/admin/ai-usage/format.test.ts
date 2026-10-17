import { describe, expect, it } from 'vitest'
import type { ApiQuota } from '../../../types/aiUsage'
import { fmtSeconds, fmtUntil, quotaView } from './format'

const NOW = Date.parse('2026-10-16T12:00:00Z')

function quota(fields: Partial<ApiQuota>): ApiQuota {
  return {
    provider: 'brave',
    label: 'Brave Search',
    configured: true,
    source: 'headers',
    plan: null,
    monthly_price: null,
    limit: null,
    remaining: null,
    used: null,
    extra_credits: null,
    resets_at: null,
    observed_at: null,
    error: null,
    note: null,
    ...fields,
  }
}

describe('fmtUntil', () => {
  it('counts down to a reset', () => {
    expect(fmtUntil('2026-10-31T12:00:00Z', NOW)).toBe('in 15d')
    expect(fmtUntil('2026-10-16T17:30:00Z', NOW)).toBe('in 5h')
    expect(fmtUntil('2026-10-16T12:20:00Z', NOW)).toBe('within the hour')
    expect(fmtUntil('2026-10-15T00:00:00Z', NOW)).toBe('passed')
  })

  it('leaves an unparseable date as it came', () => {
    expect(fmtUntil('soon', NOW)).toBe('soon')
  })
})

describe('fmtSeconds', () => {
  it('reads seconds and minutes', () => {
    expect(fmtSeconds(null)).toBe('—')
    expect(fmtSeconds(4.25)).toBe('4.3s')
    expect(fmtSeconds(42)).toBe('42s')
    expect(fmtSeconds(125)).toBe('2m 5s')
  })
})

describe('quotaView', () => {
  it('says when there is no key', () => {
    const view = quotaView(quota({ configured: false }), NOW)
    expect(view).toMatchObject({ headline: 'Not set up', tone: 'muted', leftShare: null })
  })

  it('shows the account error', () => {
    const view = quotaView(quota({ error: 'HTTP 401' }), NOW)
    expect(view).toMatchObject({ headline: 'Unavailable', detail: 'HTTP 401', tone: 'error' })
  })

  it('waits for the first Brave response', () => {
    expect(quotaView(quota({}), NOW).headline).toBe('Not seen yet')
    expect(quotaView(quota({ source: 'account_api' }), NOW).headline).toBe('Unknown')
  })

  it('shows what is left and when it resets', () => {
    const view = quotaView(quota({ limit: 2000, remaining: 1849, resets_at: '2026-10-31T12:00:00Z' }), NOW)
    expect(view.headline).toBe('1,849 left')
    expect(view.detail).toBe('of 2,000 this period · resets in 15d')
    expect(view.tone).toBe('ok')
    expect(view.leftShare).toBeCloseTo(0.9245)
  })

  it('warns under a tenth left and when it is spent', () => {
    expect(quotaView(quota({ limit: 2000, remaining: 150 }), NOW).tone).toBe('low')
    expect(quotaView(quota({ limit: 2000, remaining: 0 }), NOW)).toMatchObject({ tone: 'out', leftShare: 0 })
  })

  it('notes a reset that happened since the last response', () => {
    const view = quotaView(quota({ limit: 2000, remaining: 3, resets_at: '2026-10-01T00:00:00Z' }), NOW)
    expect(view.detail).toBe('of 2,000 this period · reset since last seen')
  })
})
