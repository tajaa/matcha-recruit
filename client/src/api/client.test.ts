import { describe, it, expect } from 'vitest'
import { API_BASE, ApiError } from './client'

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
