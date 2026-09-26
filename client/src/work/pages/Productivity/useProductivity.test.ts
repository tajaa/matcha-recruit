import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useProductivity } from './useProductivity'
import type { ProductivityCard } from '../../api/matchaWork/productivity'

const mock = vi.hoisted(() => ({
  listBoards: vi.fn(), listCards: vi.fn(), updateCard: vi.fn(),
}))
vi.mock('../../api/matchaWork/productivity', () => ({
  listProductivityBoards: mock.listBoards,
  listProductivityCards: mock.listCards,
  updateProductivityCard: mock.updateCard,
}))

const card: ProductivityCard = {
  id: 'card-one', board_id: 'board-one', title: 'A task', notes: null,
  board_column: 'todo', position: 0, due_date: '2026-01-01',
  source_journal_id: null, source_excerpt: null, completed_at: null,
  created_at: '', updated_at: '',
}

beforeEach(() => {
  vi.clearAllMocks()
  mock.listBoards.mockResolvedValue([{ id: 'board-one', title: 'Board', is_default: true, status: 'active', todo_count: 1, in_progress_count: 0, done_count: 0 }])
  mock.listCards.mockResolvedValue([card])
  mock.updateCard.mockImplementation(async (_id: string, patch: object) => ({ ...card, ...patch }))
})

async function loaded() {
  const hook = renderHook(() => useProductivity())
  await waitFor(() => expect(hook.result.current.cards).toHaveLength(1))
  return hook
}

describe('productivity card patches', () => {
  it('moves a card with only board_column and position', async () => {
    const { result } = await loaded()
    await act(async () => { await result.current.moveCard('card-one', 'in_progress') })
    expect(mock.updateCard).toHaveBeenCalledWith('card-one', { board_column: 'in_progress', position: 0 })
  })

  it('drops on a calendar day with only due_date', async () => {
    const { result } = await loaded()
    await act(async () => { await result.current.setCardDate('card-one', '2026-01-02') })
    expect(mock.updateCard).toHaveBeenCalledWith('card-one', { due_date: '2026-01-02' })
  })

  it('clears a date with an explicit null', async () => {
    const { result } = await loaded()
    await act(async () => { await result.current.setCardDate('card-one', null) })
    expect(mock.updateCard).toHaveBeenCalledWith('card-one', { due_date: null })
  })
})
