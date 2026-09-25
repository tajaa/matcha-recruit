import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ProductivityCard } from '../../api/matchaWork/productivity'
import { calendarDays, cardsOnDay, localDateKey } from './calendarMath'

function localeFirstWeekday(): number {
  try {
    const locale = new Intl.Locale(navigator.language) as Intl.Locale & {
      weekInfo?: { firstDay: number }
      getWeekInfo?: () => { firstDay: number }
    }
    return (locale.weekInfo?.firstDay ?? locale.getWeekInfo?.().firstDay ?? 7) % 7
  }
  catch { return 0 }
}

export default function CalendarPane({ cards, base, onAdd, onDate, onDelete }: {
  cards: ProductivityCard[]
  base: string
  onAdd: (title: string, dueDate: string) => Promise<unknown>
  onDate: (cardId: string, dueDate: string | null) => Promise<unknown>
  onDelete: (cardId: string) => Promise<unknown>
}) {
  const [month, setMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1))
  const [selectedDay, setSelectedDay] = useState(() => localDateKey(new Date()))
  const [title, setTitle] = useState('')
  const [dropDay, setDropDay] = useState<string | null>(null)
  const [error, setError] = useState('')
  const firstWeekday = localeFirstWeekday()
  const days = calendarDays(month.getFullYear(), month.getMonth(), firstWeekday)
  const weekdays = Array.from({ length: 7 }, (_, index) => new Intl.DateTimeFormat(undefined, { weekday: 'short' }).format(new Date(2023, 0, 1 + (index + firstWeekday) % 7)))

  async function add() {
    const trimmed = title.trim()
    setTitle('')
    if (!trimmed) return
    try { await onAdd(trimmed, selectedDay); setError('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not add card') }
  }

  function shift(amount: number) { setMonth(new Date(month.getFullYear(), month.getMonth() + amount, 1)) }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
      <div className="mb-3 flex items-center gap-3">
        <button onClick={() => shift(-1)} aria-label="Previous month"><ChevronLeft size={17} /></button>
        <h2 className="min-w-36 text-sm font-semibold">{new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' }).format(month)}</h2>
        <button onClick={() => shift(1)} aria-label="Next month"><ChevronRight size={17} /></button>
        <button onClick={() => { const today = new Date(); setMonth(new Date(today.getFullYear(), today.getMonth(), 1)); setSelectedDay(localDateKey(today)) }} className="ml-auto text-xs text-w-accent">Today</button>
      </div>
      <form onSubmit={(event) => { event.preventDefault(); void add() }} className="mb-3 flex gap-2">
        <input aria-label={`Add a card on ${selectedDay}`} value={title} onChange={(event) => setTitle(event.target.value)} placeholder={`Add a card on ${selectedDay}…`} className="min-w-0 flex-1 rounded-md border border-w-line bg-w-surface2 px-3 py-2 text-xs text-w-text" />
        <button type="submit" className="rounded-md bg-w-accent px-3 text-xs font-medium text-black">Add</button>
      </form>
      {error && <p role="alert" className="mb-2 text-xs text-red-400">{error}</p>}
      <div className="w-full flex-1 overflow-x-auto"><div className="min-w-[650px]">
        <div className="grid grid-cols-7 gap-1 text-center text-[10px] uppercase text-w-faint">{weekdays.map((day, index) => <div key={index} className="py-1">{day}</div>)}</div>
        <div className="grid grid-cols-7 gap-1">
          {days.map((day) => {
            const key = localDateKey(day)
            const sameMonth = day.getMonth() === month.getMonth()
            const today = key === localDateKey(new Date())
            const dayCards = cardsOnDay(cards, day)
            return (
              <div key={key} onClick={() => setSelectedDay(key)} onDragOver={(event) => { event.preventDefault(); setDropDay(key) }} onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDropDay(null) }} onDrop={(event) => {
                event.preventDefault(); setDropDay(null)
                const cardId = event.dataTransfer.getData('text/plain')
                if (cardId) void onDate(cardId, key).catch((cause: unknown) => setError(String(cause)))
              }} className={`h-[94px] overflow-hidden rounded-md border p-1 text-left ${dropDay === key ? 'border-w-accent bg-w-accent/10' : selectedDay === key ? 'border-w-accent/60 bg-w-accent/10' : 'border-w-line bg-w-surface/50'} ${sameMonth ? '' : 'opacity-40'}`}>
                <span className={`text-[11px] ${today ? 'font-bold text-w-accent' : 'text-w-text'}`}>{day.getDate()}</span>
                {dayCards.slice(0, 4).map((card) => <div key={card.id} draggable onDragStart={(event) => event.dataTransfer.setData('text/plain', card.id)} className={`group flex items-center gap-1 truncate rounded px-1 text-[9px] ${card.board_column === 'done' ? 'bg-w-line text-w-faint line-through' : card.board_column === 'in_progress' ? 'bg-orange-500/20 text-orange-300' : 'bg-w-accent/20 text-w-text'}`} title={card.title}>
                  <span className="min-w-0 flex-1 truncate">{card.title}</span>
                  {card.source_journal_id && <Link to={`${base}/journals/${card.source_journal_id}`} onClick={(event) => event.stopPropagation()} title={card.source_excerpt ?? 'Open source journal'} className="text-w-accent">↗</Link>}
                  <button onClick={(event) => { event.stopPropagation(); void onDate(card.id, null).catch((cause: unknown) => setError(String(cause))) }} title="Remove from calendar" aria-label={`Remove ${card.title} from calendar`} className="hidden group-hover:block">×</button>
                  <button onClick={(event) => { event.stopPropagation(); void onDelete(card.id).catch((cause: unknown) => setError(String(cause))) }} title="Delete card" aria-label={`Delete ${card.title}`} className="hidden group-hover:block">🗑</button>
                </div>)}
                {dayCards.length > 4 && <span className="text-[9px] text-w-faint">+{dayCards.length - 4} more</span>}
              </div>
            )
          })}
        </div>
      </div></div>
    </div>
  )
}
