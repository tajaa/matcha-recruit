import type { ReactNode } from 'react'

// 29 admin pages hand-roll the same <thead>/<tbody> block (79 files app-wide
// hand-roll a <table>), so the chrome drifts: a page picks px-3 instead of
// px-4, forgets the divide-y, or renders its own "no rows" copy. This is that
// markup, verbatim from pages/admin/Companies.tsx, behind a columns array.
//
// Deliberately NOT included in v1: sorting, pagination, and a search hook.
// Search in these pages is a one-line `.filter` over the rows the page already
// holds, and adding a sort API before a second caller needs it would be
// guessing at the shape.

export type Column<T> = {
  /** Stable key for React and for callers to reference a column by name. */
  key: string
  header: ReactNode
  /** Cell contents. Closures capture the page's own handlers, so row buttons
   *  move into the table unchanged. */
  render: (row: T) => ReactNode
  align?: 'left' | 'right' | 'center'
  /** Extra classes on this column's <td> (widths, whitespace control). */
  className?: string
}

type Props<T> = {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  loading?: boolean
  loadingText?: string
  emptyText?: string
  onRowClick?: (row: T) => void
}

const alignClass = { left: 'text-left', right: 'text-right', center: 'text-center' } as const

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading = false,
  loadingText = 'Loading...',
  emptyText = 'No results.',
  onRowClick,
}: Props<T>) {
  // Loading and empty are the table's job: every hand-rolled copy re-implemented
  // this ladder, and several disagreed about whether an in-flight reload should
  // blank the rows. It should not — useAsync keeps the previous page visible.
  if (loading && rows.length === 0) return <p className="text-sm text-zinc-500">{loadingText}</p>
  if (rows.length === 0) return <p className="text-sm text-zinc-500">{emptyText}</p>

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-800">
      {/* Wide tables scroll inside their own container rather than pushing the
          page into a horizontal scroll. */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="bg-zinc-900/50 text-zinc-400">
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  className={`px-4 py-3 font-medium ${alignClass[c.align ?? 'left']}`}
                >
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {rows.map((row) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={`text-zinc-300 ${onRowClick ? 'cursor-pointer hover:bg-zinc-900/40' : ''}`}
              >
                {columns.map((c) => (
                  <td
                    key={c.key}
                    className={`px-4 py-3 ${alignClass[c.align ?? 'left']} ${c.className ?? ''}`}
                  >
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
