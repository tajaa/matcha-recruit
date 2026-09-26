import { describe, expect, it } from 'vitest'
import { calendarDays, cardsOnDay, localDateKey } from './calendarMath'
import type { ProductivityCard } from '../../api/matchaWork/productivity'

describe('calendar dates', () => {
  it('uses local calendar days across month boundaries', () => {
    const days = calendarDays(2026, 0, 0)
    expect(days).toHaveLength(42)
    expect(localDateKey(days[0])).toBe('2025-12-28')
    const card = { id: 'one', due_date: '2026-01-01', position: 0 } as ProductivityCard
    expect(cardsOnDay([card], new Date(2025, 11, 31))).toEqual([])
    expect(cardsOnDay([card], new Date(2026, 0, 1))).toEqual([card])
  })
})
