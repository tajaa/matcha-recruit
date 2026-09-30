import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ getHrCaseAccess: vi.fn() }))
vi.mock('../api/hrCases', () => api)

import { resetHrCaseAccessCache, useHrCaseAccess } from './useHrCaseAccess'

beforeEach(() => { api.getHrCaseAccess.mockReset(); resetHrCaseAccessCache() })

describe('useHrCaseAccess', () => {
  it('does not ask the server when disabled', () => {
    const { result } = renderHook(() => useHrCaseAccess('u1', false))
    expect(result.current).toBe(false)
    expect(api.getHrCaseAccess).not.toHaveBeenCalled()
  })

  it('returns the server answer once per user', async () => {
    api.getHrCaseAccess.mockResolvedValue({ hr_access: true })
    const first = renderHook(() => useHrCaseAccess('u1', true))
    await waitFor(() => expect(first.result.current).toBe(true))
    const second = renderHook(() => useHrCaseAccess('u1', true))
    await waitFor(() => expect(second.result.current).toBe(true))
    expect(api.getHrCaseAccess).toHaveBeenCalledTimes(1)
  })

  it('treats a failed check as no access', async () => {
    api.getHrCaseAccess.mockRejectedValue(new Error('404'))
    const { result } = renderHook(() => useHrCaseAccess('u2', true))
    await waitFor(() => expect(api.getHrCaseAccess).toHaveBeenCalled())
    expect(result.current).toBe(false)
  })
})
