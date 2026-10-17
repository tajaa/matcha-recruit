import { useState } from 'react'

export type AdminPaginationState = {
  page: number
  pageCount: number
  pageSize: number
  total: number
  start: number
  end: number
  setPage: (page: number) => void
  setPageSize: (size: number) => void
}

/** Bound rendered rows after filtering/sorting; a changed filter starts at page one. */
export function useAdminPagination<T>(rows: readonly T[], resetKey = ''): AdminPaginationState & { rows: T[] } {
  const [state, setState] = useState({ key: resetKey, page: 1, size: 25 })
  const pageCount = Math.max(1, Math.ceil(rows.length / state.size))
  const page = state.key === resetKey ? Math.min(state.page, pageCount) : 1
  if (state.key !== resetKey || state.page !== page) setState({ ...state, key: resetKey, page })
  const offset = (page - 1) * state.size

  return {
    rows: rows.slice(offset, offset + state.size),
    page, pageCount, pageSize: state.size, total: rows.length,
    start: rows.length ? offset + 1 : 0,
    end: Math.min(offset + state.size, rows.length),
    setPage: (next) => setState((current) => ({ ...current, key: resetKey, page: Math.max(1, Math.min(next, pageCount)) })),
    setPageSize: (size) => setState({ key: resetKey, page: 1, size }),
  }
}
