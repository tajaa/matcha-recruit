import { describe, expect, it } from 'vitest'

import { inferLocationTimezone } from './locationTimezone'

describe('inferLocationTimezone', () => {
  it('maps unambiguous states to IANA timezones', () => {
    expect(inferLocationTimezone('ca')).toBe('America/Los_Angeles')
    expect(inferLocationTimezone('NY')).toBe('America/New_York')
  })

  it('requires manual selection for split-zone and exception states', () => {
    expect(inferLocationTimezone('FL')).toBeNull()
    expect(inferLocationTimezone('AZ')).toBeNull()
    expect(inferLocationTimezone('')).toBeNull()
  })
})
