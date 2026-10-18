import { useEffect, useRef, useState } from 'react'
import { Archive, ArchiveRestore, Loader2, MessageSquare, Pencil, Plus, Search, X } from 'lucide-react'
import type { AssistantConversation } from '../../api/matchaWork/assistant'
import type { AssistantSessions as Sessions } from '../../hooks/useAssistantSessions'
import { relativeTime, shortDate } from '../../../utils/format'

const TITLE_MAX = 100

/**
 * The session list beside Espresso's conversation, as on the Mac: start a
 * named session, filter, rename, and archive (kept, and restorable from the
 * Archived view). The main session can't be archived: Home's "Ask Espresso"
 * always sends there.
 */
export default function AssistantSessions({ sessions, activeId, onSelect, onClose }: {
  sessions: Sessions
  activeId: string | null
  onSelect: (id: string) => void
  /** Set when shown over the conversation on a narrow screen. */
  onClose?: () => void
}) {
  const [filter, setFilter] = useState('')
  const [creating, setCreating] = useState<{ title: string; requestId: string } | null>(null)
  const [renaming, setRenaming] = useState<{ id: string; title: string } | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const { busy, error } = sessions

  const query = filter.trim().toLowerCase()
  const source = showArchived ? (sessions.archived ?? []) : sessions.sessions
  const visible = query ? source.filter((c) => c.title.toLowerCase().includes(query)) : source
  const more = showArchived ? sessions.archivedHasMore : sessions.hasMore
  const listLoading = showArchived ? sessions.archived === null : !sessions.loaded

  async function create() {
    const title = creating?.title.trim()
    if (!creating || !title) return
    const id = await sessions.create(title, creating.requestId)
    if (!id) return
    setCreating(null)
    setShowArchived(false)
    setFilter('')
    onSelect(id)
  }

  async function rename() {
    if (!renaming) return
    const title = renaming.title.trim()
    const current = [...sessions.sessions, ...(sessions.archived ?? [])].find((c) => c.id === renaming.id)
    // Blank or unchanged (a blur after Enter, or a click away): nothing to save.
    if (!title || title === current?.title) { setRenaming(null); return }
    if (await sessions.rename(renaming.id, title)) setRenaming(null)
  }

  async function archive(item: AssistantConversation) {
    if (!(await sessions.archive(item.id)) || item.id !== activeId) return
    // Leave the archived session for the next one up, or the main one.
    const next = sessions.sessions.find((c) => c.id !== item.id)
    if (next) onSelect(next.id)
  }

  function toggleArchived() {
    if (!showArchived) void sessions.loadArchived()
    setShowArchived((v) => !v)
    setRenaming(null)
  }

  return (
    <aside className="flex h-full w-full flex-col bg-w-surface md:w-60 md:shrink-0 md:border-r md:border-w-line">
      <div className="flex items-center gap-2 px-3 pt-3">
        <h2 className="flex-1 text-[13px] font-semibold text-w-text">{showArchived ? 'Archived sessions' : 'Sessions'}</h2>
        {onClose && (
          <button type="button" onClick={onClose} aria-label="Close sessions"
            className="rounded-md p-1 text-w-dim hover:bg-w-surface2 hover:text-w-text">
            <X size={15} />
          </button>
        )}
      </div>

      <div className="space-y-2 px-3 py-2">
        {creating ? (
          <form onSubmit={(e) => { e.preventDefault(); void create() }} className="space-y-1.5">
            <NameInput
              value={creating.title}
              label="Name the new session"
              onChange={(title) => setCreating({ ...creating, title })}
              onCancel={() => setCreating(null)}
            />
            <div className="flex gap-1.5">
              <button type="submit" disabled={busy || !creating.title.trim()}
                className="flex-1 rounded-md bg-w-accent px-2 py-1 text-xs font-semibold text-white disabled:opacity-50">
                {busy ? 'Starting…' : 'Start session'}
              </button>
              <button type="button" onClick={() => setCreating(null)}
                className="rounded-md border border-w-line px-2 py-1 text-xs text-w-dim hover:text-w-text">Cancel</button>
            </div>
          </form>
        ) : (
          <button type="button" disabled={busy}
            onClick={() => { sessions.clearError(); setCreating({ title: '', requestId: crypto.randomUUID() }) }}
            className="flex w-full items-center justify-center gap-1.5 rounded-md border border-w-line px-2 py-1.5 text-xs font-semibold text-w-text hover:bg-w-surface2 disabled:opacity-50">
            <Plus size={13} /> New session
          </button>
        )}
        <div className="relative">
          <Search size={12} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-w-faint" />
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter sessions"
            aria-label="Filter sessions"
            className="w-full rounded-md border border-w-line bg-w-surface2/60 py-1.5 pl-7 pr-2 text-xs text-w-text outline-none placeholder:text-w-faint focus:border-w-accent/50" />
        </div>
        {error && <p role="alert" className="text-[11px] text-amber-500">{error}</p>}
      </div>

      <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-2" aria-label={showArchived ? 'Archived sessions' : 'Sessions'}>
        {listLoading && <li className="flex justify-center py-3"><Loader2 size={14} className="animate-spin text-w-dim" /></li>}
        {!listLoading && visible.length === 0 && (
          <li className="px-2.5 py-2 text-[11px] text-w-faint">
            {query ? 'No matching sessions' : showArchived ? 'Nothing archived' : 'No sessions yet'}
          </li>
        )}
        {visible.map((item) => {
          const active = item.id === activeId
          return (
            <li key={item.id}
              className={`group flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px] transition-colors ${
                active ? 'bg-w-surface2 font-medium text-white' : 'text-w-dim hover:bg-w-surface2/50 hover:text-w-text'}`}>
              <MessageSquare size={14} strokeWidth={1.6} className="shrink-0" />
              {renaming?.id === item.id ? (
                <form className="min-w-0 flex-1" onSubmit={(e) => { e.preventDefault(); void rename() }}>
                  <NameInput value={renaming.title} label={`Rename ${item.title}`}
                    onChange={(title) => setRenaming({ ...renaming, title })} onCancel={() => setRenaming(null)}
                    onBlur={() => void rename()} />
                </form>
              ) : (
                <>
                  <button type="button" onClick={() => onSelect(item.id)} aria-current={active ? 'page' : undefined}
                    title={item.title} className="min-w-0 flex-1 truncate text-left">
                    {item.title}
                  </button>
                  <span className="shrink-0 text-[10px] font-normal text-w-faint group-focus-within:hidden group-hover:hidden">
                    {relativeTime(item.updated_at, { empty: '', justNowLabel: 'now', maxRelativeDays: 7, absolute: shortDate }).replace(' ago', '')}
                  </span>
                  <span className="hidden shrink-0 items-center gap-0.5 group-focus-within:flex group-hover:flex">
                    <RowAction label={`Rename ${item.title}`} disabled={busy}
                      onClick={() => { sessions.clearError(); setRenaming({ id: item.id, title: item.title }) }}>
                      <Pencil size={11} />
                    </RowAction>
                    {showArchived ? (
                      <RowAction label={`Restore ${item.title}`} disabled={busy} onClick={() => void sessions.restore(item.id)}>
                        <ArchiveRestore size={11} />
                      </RowAction>
                    ) : !item.main && (
                      <RowAction label={`Archive ${item.title}`} disabled={busy} onClick={() => void archive(item)}>
                        <Archive size={11} />
                      </RowAction>
                    )}
                  </span>
                </>
              )}
            </li>
          )
        })}
        {more && !query && (
          <li>
            <button type="button" disabled={busy} onClick={() => void sessions.loadMore(showArchived ? 'archived' : 'active')}
              className="w-full px-2.5 py-1 text-left text-[11px] text-w-faint hover:text-w-text disabled:opacity-50">
              Load older sessions
            </button>
          </li>
        )}
      </ul>

      <div className="border-t border-w-line px-3 py-2">
        <button type="button" onClick={toggleArchived} aria-pressed={showArchived}
          className="flex items-center gap-1.5 text-[11px] text-w-dim hover:text-w-text">
          <Archive size={12} /> {showArchived ? 'Back to sessions' : 'Archived sessions'}
        </button>
      </div>
    </aside>
  )
}

function NameInput({ value, label, onChange, onCancel, onBlur }: {
  value: string
  label: string
  onChange: (value: string) => void
  onCancel: () => void
  onBlur?: () => void
}) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => { ref.current?.focus(); ref.current?.select() }, [])
  return (
    <input ref={ref} value={value} maxLength={TITLE_MAX} aria-label={label} placeholder="e.g. Apartment hunt"
      onChange={(e) => onChange(e.target.value)} onBlur={onBlur}
      onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); onCancel() } }}
      className="w-full rounded-md border border-w-accent/50 bg-w-surface2 px-2 py-1 text-xs text-w-text outline-none" />
  )
}

function RowAction({ label, disabled, onClick, children }: {
  label: string
  disabled?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={label} title={label.split(' ')[0]}
      className="rounded p-0.5 text-w-dim hover:text-w-text disabled:opacity-50">
      {children}
    </button>
  )
}
