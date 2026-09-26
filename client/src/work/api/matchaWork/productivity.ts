import { api } from '../../../api/client'

export type ProductivityColumn = 'todo' | 'in_progress' | 'done'

export interface ProductivityBoard {
  id: string
  title: string
  is_default: boolean
  status: 'active' | 'archived'
  created_at: string
  updated_at: string
  todo_count: number | null
  in_progress_count: number | null
  done_count: number | null
}

export interface ProductivityCard {
  id: string
  board_id: string
  title: string
  notes: string | null
  board_column: ProductivityColumn
  position: number
  due_date: string | null
  source_journal_id: string | null
  source_excerpt: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export type ProductivityCardPatch = Partial<Pick<ProductivityCard, 'title' | 'notes' | 'board_column' | 'position' | 'due_date'>>

const boardPath = (id: string) => `/matcha-work/productivity/boards/${encodeURIComponent(id)}`
const cardPath = (id: string) => `/matcha-work/productivity/cards/${encodeURIComponent(id)}`

export const listProductivityBoards = () => api.get<ProductivityBoard[]>('/matcha-work/productivity/boards')
export const createProductivityBoard = (title: string) => api.post<ProductivityBoard>('/matcha-work/productivity/boards', { title })
export const updateProductivityBoard = (id: string, patch: { title?: string; status?: 'active' | 'archived' }) => api.patch<ProductivityBoard>(boardPath(id), patch)
export const deleteProductivityBoard = (id: string) => api.delete<null>(boardPath(id))

export const listProductivityCards = (boardId: string) => api.get<ProductivityCard[]>(`${boardPath(boardId)}/cards`)
export const createProductivityCard = (boardId: string, body: { title: string; notes?: string; board_column?: ProductivityColumn; due_date?: string | null; source_journal_id?: string; source_excerpt?: string }) =>
  api.post<ProductivityCard>(`${boardPath(boardId)}/cards`, body)
export const updateProductivityCard = (id: string, patch: ProductivityCardPatch) => api.patch<ProductivityCard>(cardPath(id), patch)
export const deleteProductivityCard = (id: string) => api.delete<null>(cardPath(id))

export const createQuickTodo = (body: { title: string; due_date?: string; source_journal_id?: string; source_excerpt?: string }) =>
  api.post<ProductivityCard>('/matcha-work/productivity/quick-todo', body)
