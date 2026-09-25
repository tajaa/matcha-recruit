import type { ProductivityCard } from '../../api/matchaWork/productivity'

export function localDateKey(day: Date): string {
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
}

export function calendarDays(year: number, month: number, firstWeekday = 0): Date[] {
  const first = new Date(year, month, 1)
  const offset = (first.getDay() - firstWeekday + 7) % 7
  return Array.from({ length: 42 }, (_, index) => new Date(year, month, 1 - offset + index))
}

export function cardsOnDay(cards: ProductivityCard[], day: Date): ProductivityCard[] {
  const key = localDateKey(day)
  return cards.filter((card) => card.due_date === key).sort((a, b) => a.position - b.position)
}
