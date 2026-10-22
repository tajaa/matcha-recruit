import { useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import type { CappeSocialChatSummary } from '../../../types'

function ago(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m`
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)}h`
  return `${Math.round(minutes / (60 * 24))}d`
}

/** The Social chat's past conversations: open one, start a new one, rename
 *  or delete. A dot marks a chat whose plan is still waiting on you. */
export default function ChatList({ chats, current, onOpen, onNew, onRename, onDelete }: {
  chats: CappeSocialChatSummary[] | null
  current: string | null
  onOpen: (id: string) => void
  onNew: () => void
  onRename: (id: string, title: string) => void
  onDelete: (id: string) => void
}) {
  const [renaming, setRenaming] = useState<string | null>(null)
  const [draft, setDraft] = useState('')

  function finish(id: string) {
    const title = draft.trim()
    const before = chats?.find((c) => c.id === id)?.title
    if (title && title !== before) onRename(id, title)
    setRenaming(null)
  }

  return (
    <nav aria-label="Chats" className="space-y-1">
      <button type="button" onClick={onNew}
        className="flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-xs font-medium text-lime-300 hover:bg-zinc-800">
        <Plus className="h-3.5 w-3.5" /> New chat
      </button>
      {chats !== null && chats.length === 0 && <p className="px-2 py-3 text-xs text-zinc-500">Your chats show up here.</p>}
      {(chats ?? []).map((c) => (
        <div key={c.id} className={`group flex items-start gap-1 rounded-lg px-2 py-1.5 ${c.id === current ? 'bg-zinc-800' : 'hover:bg-zinc-800/60'}`}>
          {renaming === c.id ? (
            <input autoFocus value={draft} aria-label="Chat name" maxLength={120}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={() => finish(c.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') finish(c.id)
                if (e.key === 'Escape') { e.stopPropagation(); setRenaming(null) }
              }}
              className="min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-950 px-1.5 py-1 text-xs text-zinc-100 outline-none focus:border-lime-500" />
          ) : (
            <>
              <button type="button" onClick={() => onOpen(c.id)} className="min-w-0 flex-1 text-left">
                <span className={`flex items-center gap-1.5 truncate text-xs ${c.id === current ? 'font-medium text-zinc-100' : 'text-zinc-300'}`}>
                  {c.plan_status === 'proposed' && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-lime-400" aria-label="Plan waiting" />}
                  <span className="truncate">{c.title}</span>
                </span>
                <span className="mt-0.5 block truncate text-[11px] text-zinc-500">
                  {ago(c.updated_at)}{c.last ? ` · ${c.last}` : ''}
                </span>
              </button>
              <button type="button" onClick={() => { setRenaming(c.id); setDraft(c.title) }} aria-label={`Rename ${c.title}`}
                className="shrink-0 p-1 text-zinc-600 hover:text-zinc-200 sm:opacity-0 sm:group-hover:opacity-100">
                <Pencil className="h-3 w-3" />
              </button>
              <button type="button" onClick={() => onDelete(c.id)} aria-label={`Delete ${c.title}`}
                className="shrink-0 p-1 text-zinc-600 hover:text-red-400 sm:opacity-0 sm:group-hover:opacity-100">
                <Trash2 className="h-3 w-3" />
              </button>
            </>
          )}
        </div>
      ))}
    </nav>
  )
}
