import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetAuthCaches } from '../../api/authReset'
import { rememberRecapPreferences, useRecapPreferences } from './useRecapPreferences'

const mock = vi.hoisted(() => ({ get: vi.fn(), owner: 'owner-a' }))
vi.mock('../api/matchaWork/recaps', () => ({ getRecapPreferences: mock.get }))
vi.mock('../../hooks/useMe', () => ({ useMe: () => ({ me: { user: { id: mock.owner } }, isPersonal: true }) }))
vi.mock('../routes/WorkSurfaceContext', () => ({ useWorkSurface: () => 'espresso' }))
const off = { enabled: false, email_enabled: false, available: true }
beforeEach(() => { resetAuthCaches(); vi.clearAllMocks(); mock.owner = 'owner-a' })

describe('recap preferences', () => {
  it('shares one read and updates mounted consumers immediately after save and logout', async () => {
    mock.get.mockResolvedValue(off)
    const first = renderHook(() => useRecapPreferences())
    const second = renderHook(() => useRecapPreferences())
    await waitFor(() => expect(first.result.current).toEqual(off))
    expect(second.result.current).toEqual(off)
    expect(mock.get).toHaveBeenCalledTimes(1)
    const on = { ...off, enabled: true }
    act(() => rememberRecapPreferences('owner-a', on))
    expect(first.result.current).toEqual(on)
    expect(second.result.current).toEqual(on)
    act(resetAuthCaches)
    expect(first.result.current).toBeNull()
    expect(second.result.current).toBeNull()
  })
  it('does not restore an older read after a save or auth reset', async () => {
    let resolve!: (value: typeof off) => void
    mock.get.mockReturnValue(new Promise<typeof off>((done) => { resolve = done }))
    const view = renderHook(() => useRecapPreferences())
    act(() => rememberRecapPreferences('owner-a', { ...off, enabled: true }))
    await act(async () => resolve(off))
    expect(view.result.current?.enabled).toBe(true)
    act(resetAuthCaches)
    expect(view.result.current).toBeNull()
    mock.owner = 'owner-b'
    mock.get.mockResolvedValue(off)
    view.rerender()
    await waitFor(() => expect(view.result.current).toEqual(off))
  })
})
