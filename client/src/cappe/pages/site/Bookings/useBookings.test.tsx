import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useBookings } from './useBookings'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), delete: vi.fn(), patch: vi.fn() }))
vi.mock('../../../api', () => ({ cappeApi: api }))
const me = vi.hoisted(() => ({ account: { account_type: 'personal', plan: 'creator' } as { account_type: string; plan: string } }))
vi.mock('../../../hooks/useCappeMe', () => ({ useCappeMe: () => ({ account: me.account }) }))

const LOC = 'loc-1'
const shared = { weekday: 0, start_time: '09:00:00', end_time: '12:00:00', booking_type_id: null, staff_id: null, location_id: null }
const own = { weekday: 1, start_time: '13:00:00', end_time: '17:00:00', booking_type_id: null, staff_id: null, location_id: LOC }

function wrapper({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter initialEntries={['/sites/s-1/bookings']}>
      <Routes><Route path="/sites/:siteId/bookings" element={<>{children}</>} /></Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset()
  api.get.mockImplementation((path: string) => {
    if (path === '/sites/s-1') return Promise.resolve({ is_multi_location: true, timezone: 'UTC' })
    if (path === '/sites/s-1/locations') return Promise.resolve([{ id: LOC, name: 'Mission', active: true, is_default: true }])
    if (path.startsWith('/sites/s-1/availability')) return Promise.resolve([shared, own])
    return Promise.resolve([])
  })
})

async function loaded() {
  const hook = renderHook(() => useBookings(), { wrapper })
  await waitFor(() => expect(hook.result.current.loading).toBe(false))
  return hook
}

describe('useBookings — a location saves only its own rows', () => {
  it('marks the shared rows and never sends them as the location’s', async () => {
    const { result } = await loaded()
    expect(result.current.selLoc).toBe(LOC)
    expect(result.current.isShared(result.current.slots[0])).toBe(true)
    expect(result.current.isShared(result.current.slots[1])).toBe(false)

    api.put.mockResolvedValueOnce([own])
    await act(() => result.current.saveAvailability())
    const [path, body] = api.put.mock.calls[0]
    expect(path).toBe(`/sites/s-1/availability?location_id=${LOC}`)
    // Only the location's own window — the shared one used to be copied in.
    expect(body.slots).toEqual([{ weekday: 1, start_time: '13:00', end_time: '17:00', booking_type_id: null, staff_id: null }])
    // Both are still on screen afterwards.
    expect(result.current.slots).toEqual([shared, own])
  })

  it('treats a window added here as the location’s own', async () => {
    const { result } = await loaded()
    act(() => result.current.addSlot())
    const added = result.current.slots[2]
    expect(result.current.isShared(added)).toBe(false)
  })
})

describe('useBookings — the rider', () => {
  it.each([['creator', true], ['pro', true], ['free', false]])('is unlocked for a %s creator: %s', async (plan, unlocked) => {
    me.account = { account_type: 'personal', plan }
    const { result } = await loaded()
    expect(result.current.riderUnlocked).toBe(unlocked)
  })
})

describe('useBookings — actions say when they fail', () => {
  it('reports a staff member that could not be added', async () => {
    const { result } = await loaded()
    act(() => result.current.setStaffForm({ name: 'Ben', bio: '', image_url: '' }))
    api.post.mockRejectedValueOnce(new Error('Server error — try again in a moment.'))
    await act(() => result.current.addStaff({ preventDefault() {} } as React.FormEvent))
    expect(result.current.error).toBe('Server error — try again in a moment.')
  })

  it('asks before removing a staff member and keeps them if the owner backs out', async () => {
    const { result } = await loaded()
    vi.spyOn(window, 'confirm').mockReturnValueOnce(false)
    await act(() => result.current.removeStaff({ id: 'st-1', name: 'Ben' } as never))
    expect(api.delete).not.toHaveBeenCalled()
  })
})
