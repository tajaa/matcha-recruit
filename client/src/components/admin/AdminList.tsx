import type { ReactNode } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { AdminButton, AdminSelect } from './AdminUI'
import type { AdminPaginationState } from './useAdminPagination'

/** Compact list density shared by account pages and either table renderer. */
export function AdminList({ children }: { children: ReactNode }) {
  return <div className="admin-list min-w-0 [&_header]:mb-4 [&_header_h1]:text-xl [&_table]:text-xs [&_th]:px-3! [&_th]:py-2! [&_td]:px-3! [&_td]:py-2! [&_td]:align-middle">{children}</div>
}

export function AdminMetricRow({ items }: { items: readonly { label: string; value: ReactNode }[] }) {
  return <dl className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-zinc-800 pb-3">
    {items.map((item) => <div key={item.label} className="flex items-baseline gap-2">
      <dt className="text-xs text-zinc-400">{item.label}</dt>
      <dd className="text-sm font-semibold tabular-nums text-zinc-100">{item.value}</dd>
    </div>)}
  </dl>
}

export function AdminPagination({ pagination }: { pagination: AdminPaginationState }) {
  const { start, end, total, page, pageCount, pageSize, setPage, setPageSize } = pagination
  return <nav aria-label="Pagination" className="mb-2 flex flex-wrap items-center justify-between gap-3 text-xs text-zinc-400">
    <p aria-live="polite">{start.toLocaleString()}–{end.toLocaleString()} of {total.toLocaleString()}</p>
    <div className="flex items-center gap-3">
      <label className="flex items-center gap-2">Rows per page
        <AdminSelect aria-label="Rows per page" value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))} className="py-1! text-xs!">
          {[25, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
        </AdminSelect>
      </label>
      <span>Page {page} of {pageCount}</span>
      <div className="flex gap-1">
        <AdminButton aria-label="Previous page" variant="ghost" disabled={page === 1} onClick={() => setPage(page - 1)} className="p-1.5!"><ChevronLeft size={14} /></AdminButton>
        <AdminButton aria-label="Next page" variant="ghost" disabled={page === pageCount} onClick={() => setPage(page + 1)} className="p-1.5!"><ChevronRight size={14} /></AdminButton>
      </div>
    </div>
  </nav>
}
