import { describe, expect, it } from 'vitest'
import { fmtDate, fmtTime, resolutionText } from './format'

describe('sym-chat format', () => {
  it('formats times like the backend narrator', () => {
    expect(fmtTime('00:00')).toBe('12:00 AM')
    expect(fmtTime('12:30')).toBe('12:30 PM')
    expect(fmtTime('17:30')).toBe('5:30 PM')
    expect(fmtTime('bogus')).toBe('bogus')
  })

  it('formats a calendar date without timezone drift', () => {
    expect(fmtDate('2026-09-29')).toBe('Tue, Sep 29')
  })

  it('describes a resolution', () => {
    expect(resolutionText({ kind: 'decide', choice: 'Thai Palace' })).toBe('Thai Palace')
    expect(resolutionText({ kind: 'schedule', date: '2026-09-29', start: '17:30', end: '18:00', timezone: 'America/Los_Angeles' }))
      .toBe('5:30 PM–6:00 PM on Tue, Sep 29 (America/Los_Angeles)')
  })
})
