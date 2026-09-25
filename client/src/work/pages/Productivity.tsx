import { useRef, useState } from 'react'
import { CheckSquare, PanelLeftClose, PanelLeftOpen, Pencil, Plus, Trash2 } from 'lucide-react'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import BoardPane from './Productivity/BoardPane'
import CalendarPane from './Productivity/CalendarPane'
import { useProductivity } from './Productivity/useProductivity'
import type { ProductivityBoard } from '../api/matchaWork/productivity'

export default function Productivity() {
  const vm = useProductivity()
  const base = useWorkBase()
  const [railCollapsed, setRailCollapsed] = useState(false)
  const [mode, setMode] = useState<'board' | 'calendar'>('board')
  const [renaming, setRenaming] = useState<string | null>(null)
  const [renameText, setRenameText] = useState('')
  const [actionError, setActionError] = useState('')
  const committingRename = useRef<string | null>(null)

  async function createBoard() {
    try {
      const board = await vm.addBoard()
      committingRename.current = null
      setRenaming(board.id)
      setRenameText(board.title)
      setActionError('')
    } catch (cause) { setActionError(cause instanceof Error ? cause.message : 'Could not create board') }
  }

  function beginRename(board: ProductivityBoard) {
    if (vm.selectedBoardId !== board.id) vm.selectBoard(board.id)
    committingRename.current = null
    setRenaming(board.id)
    setRenameText(board.title)
  }

  async function commitRename(board: ProductivityBoard) {
    if (committingRename.current === board.id) return
    committingRename.current = board.id
    setRenaming(null)
    try { await vm.renameBoard(board, renameText); setActionError('') }
    catch (cause) { setActionError(cause instanceof Error ? cause.message : 'Could not rename board') }
  }

  async function deleteBoard(board: ProductivityBoard) {
    if (board.is_default || !window.confirm(`Delete ${board.title} and its cards?`)) return
    try { await vm.removeBoard(board); setActionError('') }
    catch (cause) { setActionError(cause instanceof Error ? cause.message : 'Could not delete board') }
  }

  return (
    <div className="flex h-full min-h-0 min-w-0 bg-w-bg text-w-text">
      {railCollapsed ? <div className="border-r border-w-line bg-w-surface p-2"><button onClick={() => setRailCollapsed(false)} aria-label="Show boards" title="Show boards"><PanelLeftOpen size={16} /></button></div> : <aside className="w-[220px] shrink-0 border-r border-w-line bg-w-surface md:min-w-[190px] md:max-w-[280px]">
        <div className="flex items-center gap-2 px-3 py-3 text-xs font-semibold"><CheckSquare size={15} /> <span className="flex-1">Boards</span><button onClick={() => setRailCollapsed(true)} aria-label="Hide boards"><PanelLeftClose size={15} /></button><button onClick={() => void createBoard()} aria-label="New board" title="New board"><Plus size={15} /></button></div>
        <div className="space-y-0.5 px-2">
          {vm.boards.map((board) => <div key={board.id} className={`group flex items-center gap-1 rounded-md px-2 py-1.5 text-xs ${vm.selectedBoardId === board.id ? 'bg-w-accent/10 text-w-text' : 'text-w-dim hover:bg-w-surface2'}`}>
            <button onClick={() => vm.selectBoard(board.id)} className="min-w-0 flex-1 truncate text-left">{board.title}</button>
            <span title="To do" className="text-w-accent">{board.todo_count ?? 0}</span>
            <span title="In progress" className="text-orange-400">{board.in_progress_count ?? 0}</span>
            <span title="Done" className="text-w-faint">{board.done_count ?? 0}</span>
            <button onClick={() => beginRename(board)} title={`Rename ${board.title}`} aria-label={`Rename ${board.title}`} className="hidden group-hover:block"><Pencil size={12} /></button>
            {!board.is_default && <button onClick={() => void deleteBoard(board)} title={`Delete ${board.title}`} aria-label={`Delete ${board.title}`} className="hidden group-hover:block"><Trash2 size={12} /></button>}
          </div>)}
        </div>
      </aside>}
      <main className="flex min-w-0 flex-1 flex-col">
        {(vm.error || actionError) && <p role="alert" className="border-b border-w-line px-4 py-2 text-xs text-red-400">{vm.error || actionError}</p>}
        {vm.loading ? <p className="p-5 text-sm text-w-faint">Loading boards…</p> : !vm.selectedBoard ? <div className="flex flex-1 flex-col items-center justify-center gap-2 text-sm text-w-faint"><CheckSquare size={32} /><p>No boards yet</p><button onClick={() => void createBoard()} className="text-w-accent">Create a board</button></div> : <>
          <header className="flex items-center gap-3 border-b border-w-line px-4 py-3">{renaming === vm.selectedBoard.id ? <input autoFocus aria-label="Board title" value={renameText} onChange={(event) => setRenameText(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void commitRename(vm.selectedBoard!); if (event.key === 'Escape') { committingRename.current = vm.selectedBoard!.id; setRenaming(null) } }} onBlur={() => void commitRename(vm.selectedBoard!)} className="min-w-0 flex-1 bg-w-surface2 px-1 text-sm font-semibold text-w-text outline-none" /> : <button onClick={() => beginRename(vm.selectedBoard!)} className="min-w-0 flex-1 truncate text-left text-sm font-semibold">{vm.selectedBoard.title}</button>}<div className="flex rounded-md border border-w-line bg-w-surface p-0.5 text-xs"><button onClick={() => setMode('board')} className={`rounded px-3 py-1 ${mode === 'board' ? 'bg-w-accent/20 text-w-accent' : 'text-w-dim'}`}>Board</button><button onClick={() => setMode('calendar')} className={`rounded px-3 py-1 ${mode === 'calendar' ? 'bg-w-accent/20 text-w-accent' : 'text-w-dim'}`}>Calendar</button></div></header>
          {mode === 'board' ? <BoardPane cards={vm.cards} base={base} onAdd={vm.addCard} onMove={vm.moveCard} onDate={vm.setCardDate} onRename={vm.renameCard} onDelete={vm.removeCard} /> : <CalendarPane cards={vm.cards} base={base} onAdd={(title, day) => vm.addCard(title, 'todo', day)} onDate={vm.setCardDate} onDelete={vm.removeCard} />}
        </>}
      </main>
    </div>
  )
}
