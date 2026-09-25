import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createProductivityBoard, createProductivityCard, deleteProductivityBoard, deleteProductivityCard,
  listProductivityBoards, listProductivityCards, updateProductivityBoard, updateProductivityCard,
  type ProductivityBoard, type ProductivityCard, type ProductivityColumn,
} from '../../api/matchaWork/productivity'

export function useProductivity() {
  const [boards, setBoards] = useState<ProductivityBoard[]>([])
  const [selectedBoardId, setSelectedBoardId] = useState<string | null>(null)
  const [cards, setCards] = useState<ProductivityCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const selectedRef = useRef<string | null>(null)

  const loadBoards = useCallback(async () => {
    try {
      const fetched = await listProductivityBoards()
      setBoards(fetched)
      const selected = selectedRef.current && fetched.some((board) => board.id === selectedRef.current)
        ? selectedRef.current : fetched[0]?.id ?? null
      if (selected !== selectedRef.current) setCards([])
      selectedRef.current = selected
      setSelectedBoardId(selected)
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load boards')
    } finally { setLoading(false) }
  }, [])

  const loadCards = useCallback(async (boardId: string) => {
    try {
      const fetched = await listProductivityCards(boardId)
      if (selectedRef.current === boardId) setCards(fetched)
      setError(null)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load cards') }
  }, [])

  useEffect(() => { const timer = window.setTimeout(() => { void loadBoards() }, 0); return () => window.clearTimeout(timer) }, [loadBoards])
  useEffect(() => { if (selectedBoardId) { const timer = window.setTimeout(() => { void loadCards(selectedBoardId) }, 0); return () => window.clearTimeout(timer) } }, [selectedBoardId, loadCards])

  function selectBoard(id: string) {
    selectedRef.current = id
    setSelectedBoardId(id)
    setCards([])
  }

  async function addBoard() {
    const board = await createProductivityBoard('New board')
    selectedRef.current = board.id
    setSelectedBoardId(board.id)
    setCards([])
    await loadBoards()
    return board
  }

  async function renameBoard(board: ProductivityBoard, title: string) {
    const trimmed = title.trim()
    if (!trimmed || trimmed === board.title) return
    const updated = await updateProductivityBoard(board.id, { title: trimmed })
    setBoards((previous) => previous.map((item) => item.id === board.id ? { ...item, ...updated } : item))
  }

  async function removeBoard(board: ProductivityBoard) {
    if (board.is_default) return
    await deleteProductivityBoard(board.id)
    await loadBoards()
  }

  async function addCard(title: string, column: ProductivityColumn = 'todo', dueDate?: string) {
    const trimmed = title.trim()
    if (!selectedBoardId || !trimmed) return
    const card = await createProductivityCard(selectedBoardId, { title: trimmed, board_column: column, ...(dueDate ? { due_date: dueDate } : {}) })
    setCards((previous) => [...previous, card])
    await loadBoards()
  }

  async function moveCard(cardId: string, column: ProductivityColumn) {
    const card = cards.find((item) => item.id === cardId)
    if (!card || card.board_column === column) return
    const position = Math.max(-1, ...cards.filter((item) => item.board_column === column).map((item) => item.position)) + 1
    setCards((previous) => previous.map((item) => item.id === cardId ? { ...item, board_column: column, position } : item))
    try {
      const updated = await updateProductivityCard(cardId, { board_column: column, position })
      setCards((previous) => previous.map((item) => item.id === cardId ? updated : item))
      await loadBoards()
    } catch (cause) {
      if (selectedBoardId) await loadCards(selectedBoardId)
      setError(cause instanceof Error ? cause.message : 'Could not move card')
    }
  }

  async function setCardDate(cardId: string, dueDate: string | null) {
    if (!cards.some((item) => item.id === cardId)) return
    setCards((previous) => previous.map((item) => item.id === cardId ? { ...item, due_date: dueDate } : item))
    try {
      const updated = await updateProductivityCard(cardId, { due_date: dueDate })
      setCards((previous) => previous.map((item) => item.id === cardId ? updated : item))
      await loadBoards()
    } catch (cause) {
      if (selectedBoardId) await loadCards(selectedBoardId)
      setError(cause instanceof Error ? cause.message : 'Could not set due date')
    }
  }

  async function renameCard(card: ProductivityCard, title: string) {
    const trimmed = title.trim()
    if (!trimmed || trimmed === card.title) return
    const updated = await updateProductivityCard(card.id, { title: trimmed })
    setCards((previous) => previous.map((item) => item.id === card.id ? updated : item))
    await loadBoards()
  }

  async function removeCard(cardId: string) {
    await deleteProductivityCard(cardId)
    setCards((previous) => previous.filter((item) => item.id !== cardId))
    await loadBoards()
  }

  return { boards, selectedBoardId, selectedBoard: boards.find((board) => board.id === selectedBoardId) ?? null,
    cards, loading, error, setError, selectBoard, addBoard, renameBoard, removeBoard,
    addCard, moveCard, setCardDate, renameCard, removeCard }
}
