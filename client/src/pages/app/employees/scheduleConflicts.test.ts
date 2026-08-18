import { describe, it, expect } from 'vitest'
import { ApiError } from '../../../api/client'
import { conflictPrompt } from './scheduleConflicts'

function err409(detail: unknown) {
  return new ApiError('conflict', 409, { detail })
}

describe('conflictPrompt', () => {
  it('returns schedule_conflict copy', () => {
    const prompt = conflictPrompt(err409({
      code: 'schedule_conflict',
      conflicts: [{ starts_at: '2026-08-03T08:00:00Z', ends_at: '2026-08-03T16:00:00Z', role: 'Opener' }],
    }))
    expect(prompt).toContain('Already scheduled during this time')
    expect(prompt).toContain('Assign anyway?')
  })

  it('returns shift_full copy', () => {
    const prompt = conflictPrompt(err409({ code: 'shift_full', message: 'Shift has 2 of 2 required staff' }))
    expect(prompt).toContain('Shift has 2 of 2 required staff')
    expect(prompt).toContain('Assign anyway?')
  })

  it('returns schedule_compliance copy', () => {
    const prompt = conflictPrompt(err409({
      code: 'schedule_compliance',
      violations: [{ check: 'meal_break', severity: 'advisory', message: 'Missing meal break' }],
    }))
    expect(prompt).toContain('Missing meal break')
    expect(prompt).toContain('Schedule anyway?')
  })

  it('returns outside_availability copy', () => {
    const prompt = conflictPrompt(err409({
      code: 'outside_availability',
      violations: [{ date: '2026-08-03', message: '2026-08-03: outside logged availability' }],
    }))
    expect(prompt).toContain("Outside this employee's logged availability")
    expect(prompt).toContain('outside logged availability')
    expect(prompt).toContain('Schedule anyway?')
  })

  it('returns qualification override copy', () => {
    const prompt = conflictPrompt(err409({
      code: 'not_qualified_for_job', message: 'Not on the qualified list for Box Office',
    }))
    expect(prompt).toContain('Not on the qualified list for Box Office')
    expect(prompt).toContain('Assign anyway?')
  })

  it('returns null for a 422', () => {
    const err = new ApiError('block', 422, { detail: { code: 'schedule_compliance_block' } })
    expect(conflictPrompt(err)).toBeNull()
  })

  it('returns null for a non-ApiError', () => {
    expect(conflictPrompt(new Error('boom'))).toBeNull()
  })
})
