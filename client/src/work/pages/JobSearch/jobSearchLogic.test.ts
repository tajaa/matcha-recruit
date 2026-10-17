import { describe, expect, it } from 'vitest'
import { ApiError } from '../../../api/client'
import type { JobLeadSummary, JobSearchDetail } from '../../api/matchaWork/jobSearch'
import {
  BELOW_FLOOR_BAND, errorCode, filterLeads, leadStatusText, parseBaseFloor, partLine, placeholders,
  progressLine, retryIsNewRequest, searchProgress, splitList, statusChanged, tidyPosting, trimNumber,
  usableApproach, webUrl, widerCount,
} from './jobSearchLogic'

function lead(overrides: Partial<JobLeadSummary> = {}): JobLeadSummary {
  return {
    id: 'l1', title: 'COO', company: 'Acme', location: 'Austin, TX', remote: false,
    source_url: null, apply_url: null, posted_text: null, comp_line: '$250,000–$300,000',
    comp_status: 'posted', fit_score: 4, screen_status: 'relevant', rank: 1, rank_band: 1,
    flags: [], user_state: 'new', approach_status: 'none', email_draft_id: null,
    email_drafted_at: null, email_sent_at: null, ...overrides,
  }
}

function detail(overrides: Partial<JobSearchDetail> = {}): JobSearchDetail {
  return {
    id: 's1', title: 'COO', ask: 'COO roles', status: 'done', progress: null, error: null,
    lead_count: 0, posted_pay_count: 0, weights: null, use_resume: false, created_at: null,
    fit_floor: 4, leads: [], fingerprint: 'f1', ...overrides,
  }
}

describe('filterLeads', () => {
  const strong = lead({ id: 'strong' })
  const weaker = lead({ id: 'weaker', rank_band: BELOW_FLOOR_BAND, fit_score: 3 })
  const screenedOut = lead({ id: 'out', screen_status: 'irrelevant' })
  const savedWeaker = lead({ id: 'savedWeaker', rank_band: BELOW_FLOOR_BAND, user_state: 'saved' })
  const dismissed = lead({ id: 'gone', user_state: 'dismissed' })
  const drafted = lead({ id: 'drafted', approach_status: 'done' })
  const unposted = lead({ id: 'unposted', comp_status: 'not_disclosed' })
  const all = [strong, weaker, screenedOut, savedWeaker, dismissed, drafted, unposted]
  const ids = (list: JobLeadSummary[]) => list.map((l) => l.id)

  it('hides weaker and screened-out jobs from the browsing tabs unless asked', () => {
    expect(ids(filterLeads(all, 'All', false))).toEqual(['strong', 'drafted', 'unposted'])
    expect(ids(filterLeads(all, 'All', true))).toEqual(['strong', 'weaker', 'out', 'savedWeaker', 'drafted', 'unposted'])
  })

  it("never hides a job from the person's own lists", () => {
    expect(ids(filterLeads(all, 'Saved', false))).toEqual(['savedWeaker'])
    expect(ids(filterLeads(all, 'Dismissed', false))).toEqual(['gone'])
  })

  it('keeps Drafted and Pay posted to what they say', () => {
    expect(ids(filterLeads(all, 'Drafted', false))).toEqual(['drafted'])
    expect(ids(filterLeads(all, 'Pay posted', false))).toEqual(['strong', 'drafted'])
  })
})

describe('widerCount', () => {
  const leads = [
    lead({ id: 'a', rank_band: BELOW_FLOOR_BAND, fit_score: 3 }),
    lead({ id: 'b', rank_band: BELOW_FLOOR_BAND, fit_score: 3, user_state: 'dismissed' }),
    lead({ id: 'c', rank_band: BELOW_FLOOR_BAND, fit_score: 2 }),
    lead({ id: 'd', rank_band: BELOW_FLOOR_BAND, fit_score: 3, screen_status: 'irrelevant' }),
  ]

  it('counts the 3/5 jobs of a finished first pass', () => {
    expect(widerCount(detail({ leads }))).toBe(1)
  })

  it('offers nothing once widened, or while the search runs', () => {
    expect(widerCount(detail({ leads, fit_floor: 3 }))).toBe(0)
    expect(widerCount(detail({ leads, status: 'screening' }))).toBe(0)
    expect(widerCount(detail({ leads, status: 'failed' }))).toBe(0)
  })
})

describe('statusChanged', () => {
  it('reloads only on a new fingerprint, status or job count', () => {
    const current = detail({ leads: [lead()] })
    const same = { id: 's1', status: 'done', progress: null, error: null, lead_count: 1, fingerprint: 'f1' }
    expect(statusChanged(current, same)).toBe(false)
    expect(statusChanged(current, { ...same, fingerprint: 'f2' })).toBe(true)
    expect(statusChanged(current, { ...same, status: 'cancelled' })).toBe(true)
    expect(statusChanged(current, { ...same, lead_count: 2 })).toBe(true)
  })
})

describe('progress', () => {
  it('counts what the person has done, leaving dismissed jobs out', () => {
    const p = searchProgress([
      lead({ user_state: 'saved', approach_status: 'done' }),
      lead({ email_draft_id: 'd1' }),
      lead({ email_draft_id: 'd2', email_sent_at: '2026-10-17T00:00:00Z' }),
      lead({ user_state: 'applied' }),
      lead({ user_state: 'dismissed', approach_status: 'done', email_draft_id: 'd3' }),
    ])
    expect(p).toEqual({ drafted: 1, saved: 1, emailsWaiting: 1, emailsSent: 1, applied: 1 })
    expect(progressLine(p)).toBe('1 saved · 1 email in drafts · 1 sent · 1 applied')
    expect(progressLine({ drafted: 3, saved: 0, emailsWaiting: 0, emailsSent: 0, applied: 0 })).toBeNull()
  })
})

describe('leadStatusText', () => {
  it("puts the person's own state first, then the email", () => {
    expect(leadStatusText(lead({ screen_status: 'irrelevant' }))).toBe('Screened out')
    expect(leadStatusText(lead({ rank_band: BELOW_FLOOR_BAND }))).toBe('Weaker fit')
    expect(leadStatusText(lead({ rank_band: BELOW_FLOOR_BAND, user_state: 'saved' }))).toBe('Saved')
    expect(leadStatusText(lead({ user_state: 'applied', email_draft_id: 'd' }))).toBe('Applied')
    expect(leadStatusText(lead({ email_draft_id: 'd', email_sent_at: 'x' }))).toBe('Emailed')
    expect(leadStatusText(lead({ email_draft_id: 'd' }))).toBe('In drafts')
    expect(leadStatusText(lead())).toBe('')
  })
})

describe('parseBaseFloor', () => {
  it('reads the ways people write a salary', () => {
    expect(parseBaseFloor('')).toEqual({ kind: 'none' })
    expect(parseBaseFloor('250000')).toEqual({ kind: 'amount', dollars: 250_000 })
    expect(parseBaseFloor('$250,000.00')).toEqual({ kind: 'amount', dollars: 250_000 })
    expect(parseBaseFloor('$250K')).toEqual({ kind: 'amount', dollars: 250_000 })
    expect(parseBaseFloor('1.5M')).toEqual({ kind: 'amount', dollars: 1_500_000 })
    expect(parseBaseFloor('1.5 mm')).toEqual({ kind: 'amount', dollars: 1_500_000 })
    expect(parseBaseFloor('250000 USD')).toEqual({ kind: 'amount', dollars: 250_000 })
  })

  it("refuses what it can't read, or more than the server takes", () => {
    expect(parseBaseFloor('about 200')).toEqual({ kind: 'invalid' })
    expect(parseBaseFloor('-5')).toEqual({ kind: 'invalid' })
    expect(parseBaseFloor('k')).toEqual({ kind: 'invalid' })
    expect(parseBaseFloor('11M')).toEqual({ kind: 'invalid' })
    expect(parseBaseFloor('1.2.3')).toEqual({ kind: 'invalid' })
  })
})

describe('splitList', () => {
  it('splits on commas, semicolons and lines, once each', () => {
    expect(splitList('COO, Chief Operating Officer;coo\n VP Ops ,')).toEqual(['COO', 'Chief Operating Officer', 'VP Ops'])
  })
})

describe('partLine', () => {
  it('writes pay the way the server does', () => {
    expect(partLine('Base', { min: 250000, max: 300000, currency: 'USD', period: 'year' })).toBe('$250,000–$300,000 a year')
    expect(partLine('Base', { min: 85.5, currency: 'USD', period: 'hour' })).toBe('$85.5 an hour')
    expect(partLine('Base', { min: 90000, max: 90000, currency: 'EUR' })).toBe('EUR 90,000')
    expect(partLine('Bonus', { pct_min: 30 })).toBe('30% of base')
    expect(partLine('Equity', { pct_min: 0.5, pct_max: 1 })).toBe('0.5–1%')
    expect(partLine('Equity', { status: 'mentioned' })).toBe('Mentioned, no figure')
    expect(partLine('Base', {})).toBe('Not posted')
  })

  it('trims numbers like Python’s :g', () => {
    expect(trimNumber(30)).toBe('30')
    expect(trimNumber(12.5)).toBe('12.5')
    expect(trimNumber(1 / 3)).toBe('0.333333')
  })
})

describe('drafts', () => {
  it('finds the blanks a draft leaves, once each', () => {
    expect(placeholders("Hi [Name],\nI'm at [Company] — [Name] again. [x]")).toEqual(['[Name]', '[Company]'])
  })

  it('treats an empty approach as none', () => {
    expect(usableApproach({})).toBeNull()
    expect(usableApproach({ steps: [] })).toBeNull()
    expect(usableApproach({ summary: 'Go through the founder.' })).not.toBeNull()
  })

  it('tidies a posting', () => {
    expect(tidyPosting('  About\u00A0us  \r\n\r\n\r\n   We   build things.\n\n')).toBe('About us\n\nWe build things.')
  })
})

describe('links and errors', () => {
  it('opens only http(s) links', () => {
    expect(webUrl('https://jobs.lever.co/acme/1')).toBe('https://jobs.lever.co/acme/1')
    expect(webUrl('javascript:alert(1)')).toBeNull()
    expect(webUrl('not a url')).toBeNull()
    expect(webUrl(null)).toBeNull()
  })

  it('starts a new request only after a clear refusal', () => {
    expect(retryIsNewRequest(new ApiError('no', 422, null))).toBe(true)
    expect(retryIsNewRequest(new ApiError('down', 503, null))).toBe(true)
    expect(retryIsNewRequest(new ApiError('gateway', 504, null))).toBe(false)
    expect(retryIsNewRequest(new TypeError('Failed to fetch'))).toBe(false)
  })

  it("reads the server's refusal code", () => {
    const body = { detail: { code: 'email_not_connected', message: 'Connect Gmail first.' } }
    expect(errorCode(new ApiError('Connect Gmail first.', 409, body))).toBe('email_not_connected')
    expect(errorCode(new ApiError('x', 409, { detail: 'plain' }))).toBeNull()
  })
})
