import { describe, it, expect } from 'vitest'
import { API_BASE, ApiError, _shouldReportStatus } from './client'

describe('API_BASE', () => {
  it('never ends with a slash (a trailing-slash VITE_API_URL would otherwise double-slash every request)', () => {
    expect(API_BASE.endsWith('/')).toBe(false)
    expect(API_BASE.length).toBeGreaterThan(0)
  })
})

describe('ApiError', () => {
  it('exposes status and body for callers branching on status', () => {
    const e = new ApiError('too many', 429, { detail: 'too many' })
    expect(e.status).toBe(429)
    expect(e.body).toEqual({ detail: 'too many' })
    expect(e.name).toBe('ApiError')
  })
})

describe('_shouldReportStatus', () => {
  it('skips expected client-input/business-rule/auth statuses', () => {
    for (const status of [400, 401, 402, 403, 404, 409, 410, 422, 429]) {
      expect(_shouldReportStatus(status)).toBe(false)
    }
  })

  it('reports network failures, 5xx, and anything unexpected', () => {
    expect(_shouldReportStatus(0)).toBe(true)
    expect(_shouldReportStatus(500)).toBe(true)
    expect(_shouldReportStatus(502)).toBe(true)
    expect(_shouldReportStatus(418)).toBe(true)
  })
})
