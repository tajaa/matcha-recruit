import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useAdminPagination } from './useAdminPagination'

describe('useAdminPagination', () => {
  it('bounds rendering, resets filters, and handles shrinking results', () => {
    const rows = Array.from({ length: 1005 }, (_, index) => index)
    const { result, rerender } = renderHook(({ rows, key }) => useAdminPagination(rows, key), { initialProps: { rows, key: 'all' } })
    expect(result.current.rows).toEqual(rows.slice(0, 25))
    expect(result.current.pageCount).toBe(41)
    act(() => result.current.setPage(41))
    expect(result.current.rows).toEqual([1000, 1001, 1002, 1003, 1004])
    expect(result.current.start).toBe(1001)
    expect(result.current.end).toBe(1005)
    rerender({ rows: [3], key: 'search' })
    expect(result.current.page).toBe(1)
    expect(result.current.rows).toEqual([3])
    rerender({ rows, key: 'all' })
    expect(result.current.page).toBe(1)
    act(() => result.current.setPageSize(100))
    expect(result.current.rows).toHaveLength(100)
    act(() => result.current.setPage(11))
    rerender({ rows: rows.slice(0, 99), key: 'all' })
    expect(result.current.page).toBe(1)
    expect(result.current.rows).toHaveLength(99)
    rerender({ rows: [], key: 'all' })
    expect(result.current).toMatchObject({ page: 1, pageCount: 1, start: 0, end: 0, rows: [] })
  })
})
