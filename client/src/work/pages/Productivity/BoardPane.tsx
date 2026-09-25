import { useRef, useState } from 'react'
import { Circle, CircleCheck, CircleDashed, Plus, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ProductivityCard, ProductivityColumn } from '../../api/matchaWork/productivity'

const columns: { key: ProductivityColumn; label: string; icon: typeof Circle }[] = [
  { key: 'todo', label: 'To Do', icon: Circle },
  { key: 'in_progress', label: 'In Progress', icon: CircleDashed },
  { key: 'done', label: 'Done', icon: CircleCheck },
]

export default function BoardPane({ cards, base, onAdd, onMove, onDate, onRename, onDelete }: {
  cards: ProductivityCard[]
  base: string
  onAdd: (title: string, column: ProductivityColumn) => Promise<unknown>
  onMove: (id: string, column: ProductivityColumn) => Promise<unknown>
  onDate: (id: string, date: string | null) => Promise<unknown>
  onRename: (card: ProductivityCard, title: string) => Promise<unknown>
  onDelete: (id: string) => Promise<unknown>
}) {
  const [adding, setAdding] = useState<ProductivityColumn | null>(null)
  const [draft, setDraft] = useState('')
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameText, setRenameText] = useState('')
  const [dragOver, setDragOver] = useState<ProductivityColumn | null>(null)
  const [error, setError] = useState('')
  const committingAdd = useRef(false)
  const committingRename = useRef<string | null>(null)

  async function add(column: ProductivityColumn) {
    if (committingAdd.current) return
    committingAdd.current = true
    const title = draft.trim()
    setAdding(null); setDraft('')
    if (!title) return
    try { await onAdd(title, column); setError('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not add card') }
  }

  async function rename(card: ProductivityCard) {
    if (committingRename.current === card.id) return
    committingRename.current = card.id
    const title = renameText.trim()
    setRenamingId(null)
    if (!title || title === card.title) return
    try { await onRename(card, title); setError('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not rename card') }
  }

  return (
    <div className="min-h-0 flex-1 overflow-x-auto p-4">
      {error && <p role="alert" className="mb-3 text-xs text-red-400">{error}</p>}
      <div className="flex min-h-full gap-3">
        {columns.map(({ key, label, icon: Icon }) => {
          const columnCards = cards.filter((card) => card.board_column === key).sort((a, b) => a.position - b.position)
          return (
            <div key={key} onDragOver={(event) => { event.preventDefault(); setDragOver(key) }} onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragOver(null) }} onDrop={(event) => {
              event.preventDefault(); setDragOver(null)
              const cardId = event.dataTransfer.getData('text/plain')
              if (cardId) void onMove(cardId, key).catch((cause: unknown) => setError(String(cause)))
            }} className={`flex min-h-60 w-[280px] shrink-0 flex-col rounded-xl border bg-w-surface p-3 ${dragOver === key ? 'border-w-accent/60 bg-w-accent/10' : 'border-w-line'}`}>
              <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-w-text"><Icon size={15} className="text-w-accent" /><span className="flex-1">{label}</span><span className="text-w-faint">{columnCards.length}</span><button onClick={() => { committingAdd.current = false; setAdding(key); setDraft('') }} title={`Add to ${label}`} aria-label={`Add to ${label}`}><Plus size={15} /></button></div>
              {adding === key && <input autoFocus aria-label={`New card in ${label}`} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void add(key); if (event.key === 'Escape') { committingAdd.current = true; setAdding(null) } }} onBlur={() => void add(key)} placeholder="Card title…" className="mb-2 w-full rounded border border-w-line bg-w-bg px-2 py-2 text-xs text-w-text" />}
              <div className="space-y-2">
                {columnCards.map((card) => <div key={card.id} draggable={renamingId !== card.id} onDragStart={(event) => { event.dataTransfer.setData('text/plain', card.id); event.dataTransfer.effectAllowed = 'move' }} className="rounded-lg border border-w-line bg-w-bg p-2.5 text-xs text-w-text shadow-sm">
                  <div className="flex items-start gap-2">
                    <button onClick={() => void onMove(card.id, card.board_column === 'done' ? 'todo' : 'done').catch((cause: unknown) => setError(String(cause)))} title={card.board_column === 'done' ? 'Mark to do' : 'Mark done'}>{card.board_column === 'done' ? <CircleCheck size={15} className="text-w-accent" /> : <Circle size={15} className="text-w-faint" />}</button>
                    {renamingId === card.id ? <input autoFocus value={renameText} onChange={(event) => setRenameText(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void rename(card); if (event.key === 'Escape') { committingRename.current = card.id; setRenamingId(null) } }} onBlur={() => void rename(card)} className="min-w-0 flex-1 bg-w-surface2 text-xs outline-none" /> : <button onClick={() => { committingRename.current = null; setRenamingId(card.id); setRenameText(card.title) }} className={`min-w-0 flex-1 text-left ${key === 'done' ? 'text-w-faint line-through' : ''}`}>{card.title}</button>}
                    <button onClick={() => void onDelete(card.id).catch((cause: unknown) => setError(String(cause)))} title="Delete card" aria-label={`Delete ${card.title}`} className="text-w-faint hover:text-red-400"><Trash2 size={13} /></button>
                  </div>
                  {card.notes && <p className="mt-2 line-clamp-2 text-w-faint">{card.notes}</p>}
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-w-faint">
                    <input type="date" aria-label={`Due date for ${card.title}`} value={card.due_date ?? ''} onChange={(event) => void onDate(card.id, event.target.value || null).catch((cause: unknown) => setError(String(cause)))} className="max-w-28 rounded bg-w-surface2 px-1 py-0.5 text-w-dim" />
                    {card.due_date && <span>{new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(new Date(`${card.due_date}T12:00:00`))}</span>}
                    {card.source_journal_id && <Link to={`${base}/journals/${card.source_journal_id}`} title={card.source_excerpt ?? 'Open source journal'} className="text-w-accent hover:underline">From journal</Link>}
                  </div>
                  <select aria-label={`Move ${card.title} to column`} value={card.board_column} onChange={(event) => void onMove(card.id, event.target.value as ProductivityColumn).catch((cause: unknown) => setError(String(cause)))} className="mt-2 rounded bg-w-surface2 px-1 py-0.5 text-[10px] text-w-dim sm:hidden">
                    {columns.map((column) => <option key={column.key} value={column.key}>{column.label}</option>)}
                  </select>
                </div>)}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
