import { useMemo, useState } from 'react'
import { Card } from '../../../../components/ui'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { ComplianceCalendarItem } from '../../../../api/compliance/compliance'
import { formatDate, localDateKey } from './helpers'

interface MonthViewProps {
  items: ComplianceCalendarItem[]
  onClick: (item: ComplianceCalendarItem) => void
}

export function MonthView({ items, onClick }: MonthViewProps) {
  const [cursor, setCursor] = useState(() => {
    const today = new Date()
    return new Date(today.getFullYear(), today.getMonth(), 1)
  })

  const monthLabel = cursor.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })

  const itemsByDate = useMemo(() => {
    const map = new Map<string, ComplianceCalendarItem[]>()
    items.forEach((i) => {
      const arr = map.get(i.deadline) ?? []
      arr.push(i)
      map.set(i.deadline, arr)
    })
    return map
  }, [items])

  const startOffset = cursor.getDay()
  const daysInMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate()
  const today = new Date()
  const todayKey = localDateKey(today)

  const cells = []
  for (let i = 0; i < startOffset; i++) cells.push(null)
  for (let day = 1; day <= daysInMonth; day++) {
    const d = new Date(cursor.getFullYear(), cursor.getMonth(), day)
    const key = localDateKey(d)
    cells.push({ day, key, items: itemsByDate.get(key) ?? [] })
  }

  // Items in the current month, and (when empty) a hint to the next one
  // that has any. Otherwise the user paging through months sees a row
  // of blank cells with no signal that the calendar is actually populated.
  const itemsInThisMonth = cells.reduce(
    (n, c) => n + (c?.items.length ?? 0),
    0,
  )
  const nextItemAfterCursor = useMemo(() => {
    if (itemsInThisMonth > 0) return null
    const monthStart = localDateKey(new Date(cursor.getFullYear(), cursor.getMonth(), 1))
    const future = items
      .filter((i) => i.deadline >= monthStart)
      .sort((a, b) => a.deadline.localeCompare(b.deadline))[0]
    return future ?? null
  }, [items, cursor, itemsInThisMonth])

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}
          className="p-1 rounded hover:bg-zinc-800 text-zinc-400"
        >
          <ChevronLeft size={18} />
        </button>
        <h2 className="text-sm font-semibold text-zinc-100">{monthLabel}</h2>
        <button
          onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}
          className="p-1 rounded hover:bg-zinc-800 text-zinc-400"
        >
          <ChevronRight size={18} />
        </button>
      </div>
      {itemsInThisMonth === 0 && (
        <div className="mb-3 px-3 py-2 rounded border border-zinc-800 bg-zinc-900/40 text-xs text-zinc-400">
          {nextItemAfterCursor ? (
            <>
              Nothing in {monthLabel}. Next deadline:{' '}
              <button
                onClick={() => {
                  const d = new Date(nextItemAfterCursor.deadline + 'T00:00:00')
                  setCursor(new Date(d.getFullYear(), d.getMonth(), 1))
                }}
                className="text-emerald-400 hover:underline"
              >
                {formatDate(nextItemAfterCursor.deadline)} — {nextItemAfterCursor.title}
              </button>
            </>
          ) : (
            <>Nothing in {monthLabel}. No deadlines on the calendar yet.</>
          )}
        </div>
      )}
      <div className="grid grid-cols-7 gap-1 text-center text-[10px] uppercase text-zinc-600 mb-1">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
          <div key={d}>{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((cell, i) =>
          cell === null ? (
            <div key={`empty-${i}`} />
          ) : (
            <div
              key={cell.key}
              className={`min-h-[64px] p-1 rounded border text-xs ${
                cell.key === todayKey
                  ? 'border-emerald-700 bg-emerald-900/10'
                  : 'border-zinc-800 bg-zinc-900/50'
              }`}
            >
              <div className="text-[10px] text-zinc-500 mb-1">{cell.day}</div>
              <div className="space-y-0.5">
                {cell.items.slice(0, 3).map((it) => (
                  <button
                    key={it.id}
                    onClick={() => onClick(it)}
                    className={`w-full text-left truncate px-1 py-0.5 rounded text-[10px] ${
                      it.derived_status === 'overdue'
                        ? 'bg-red-900/40 text-red-300'
                        : it.derived_status === 'due_soon'
                          ? 'bg-amber-900/40 text-amber-300'
                          : 'bg-zinc-800 text-zinc-300'
                    }`}
                  >
                    {it.title}
                  </button>
                ))}
                {cell.items.length > 3 && (
                  <p className="text-[10px] text-zinc-600 px-1">+{cell.items.length - 3} more</p>
                )}
              </div>
            </div>
          )
        )}
      </div>
    </Card>
  )
}
