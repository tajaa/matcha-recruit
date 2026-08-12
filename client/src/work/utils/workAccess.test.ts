import { describe, expect, it } from 'vitest'
import { ACCESS_LEVEL_COPY, canManageWorkPermissions, sourceLabel } from './workAccess'

describe('work access copy and capability helpers', () => {
  it('describes the permission ladder in increasing authority', () => {
    expect(ACCESS_LEVEL_COPY.member.short).toContain('prepare')
    expect(ACCESS_LEVEL_COPY.reviewer.short).toContain('sensitive')
    expect(ACCESS_LEVEL_COPY.operator.short).toContain('run')
    expect(ACCESS_LEVEL_COPY.admin.short).toContain('control')
  })

  it('only exposes permission management to managers', () => {
    expect(canManageWorkPermissions(['actions.execute'])).toBe(false)
    expect(canManageWorkPermissions(['permissions.manage'])).toBe(true)
    expect(canManageWorkPermissions(undefined)).toBe(false)
  })

  it('labels default and explicit sources plainly', () => {
    expect(sourceLabel('employee_default')).toBe('Default: company employee')
    expect(sourceLabel('client_default')).toBe('Default: company client')
    expect(sourceLabel('explicit')).toBe('Custom grant')
  })
})
