import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Pencil, Check, X, Sun, Moon, MoreHorizontal } from 'lucide-react'
import ThreadCollaborators from '../../components/panels/ThreadCollaborators'
import { formatTokens } from '../../components/panels/constants'
import { TASK_LABELS } from './constants'
import ToolsMenu from './ToolsMenu'
import type { ThreadTheme } from './theme'
import type { ThreadController } from './useThreadController'

interface ThreadHeaderProps {
  c: ThreadController
  th: ThreadTheme
  lm: boolean
  hasRightPanel: boolean
}

export default function ThreadHeader({ c, th, lm, hasRightPanel }: ThreadHeaderProps) {
  const {
    base, editingTitle, titleDraft, setTitleDraft, handleTitleSave, setEditingTitle,
    thread, threadId, onlineUsers, mobileView, setMobileView,
  } = c

  return (
    <div className={`flex items-center gap-3 px-4 py-3 border-b ${th.border}`}>
      <Link to={base} className={`${th.backArrow} transition-colors shrink-0`}>
        <ArrowLeft size={18} />
      </Link>

      {editingTitle ? (
        <div className="flex items-center gap-2 flex-1">
          <input
            value={titleDraft}
            onChange={(e) => setTitleDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleTitleSave()}
            className={`${th.titleInput} text-sm px-2 py-2 rounded flex-1`}
            autoFocus
          />
          <button onClick={handleTitleSave} className="text-emerald-400 hover:text-emerald-300">
            <Check size={16} />
          </button>
          <button onClick={() => setEditingTitle(false)} className="text-w-dim hover:text-w-text">
            <X size={16} />
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <h2 className={`${th.titleText} font-medium truncate`}>{thread?.title}</h2>
          <button
            onClick={() => {
              setTitleDraft(thread?.title ?? '')
              setEditingTitle(true)
            }}
            className={`${th.editBtn} transition-colors shrink-0`}
          >
            <Pencil size={14} />
          </button>
          {thread?.task_type && (
            <span className="shrink-0 text-[11px] text-w-faint truncate">
              {TASK_LABELS[thread.task_type] ?? thread.task_type}
            </span>
          )}
          {threadId && (
            <ThreadCollaborators
              threadId={threadId}
              onlineUsers={onlineUsers}
              lightMode={lm}
            />
          )}
        </div>
      )}

      {/* Mobile panel toggle */}
      {hasRightPanel && (
        <div className={`flex md:hidden rounded-full overflow-hidden shrink-0 border ${th.border}`}>
          <button
            onClick={() => setMobileView('chat')}
            className={`px-2 py-1 text-[10px] font-medium transition-colors ${
              mobileView === 'chat' ? 'bg-w-accent text-white' : 'text-w-dim'
            }`}
          >
            Chat
          </button>
          <button
            onClick={() => setMobileView('panel')}
            className={`px-2 py-1 text-[10px] font-medium transition-colors ${
              mobileView === 'panel' ? 'bg-w-accent text-white' : 'text-w-dim'
            }`}
          >
            Panel
          </button>
        </div>
      )}

      <ToolsMenu c={c} />
      <HeaderOverflow c={c} th={th} />
    </div>
  )
}

function HeaderOverflow({ c, th }: { c: ThreadController; th: ThreadTheme }) {
  const { lightMode, toggleLightMode, usage24h, usageTotal } = c
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  const has24h = !!usage24h?.totals.total_tokens
  const hasTotal = !!usageTotal?.totals.total_tokens

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`p-1.5 rounded-full transition-colors ${th.backArrow}`}
        title="More"
      >
        <MoreHorizontal size={16} />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-2 w-56 rounded-lg border border-w-line bg-w-surface shadow-xl z-50 text-xs">
          {(has24h || hasTotal) && (
            <div className="px-3 py-2 border-b border-w-line font-mono text-[11px] text-w-faint">
              {has24h && <div>24h: {formatTokens(usage24h!.totals.total_tokens)}</div>}
              {hasTotal && <div>30d: {formatTokens(usageTotal!.totals.total_tokens)}</div>}
            </div>
          )}
          <button
            onClick={toggleLightMode}
            className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-w-surface2/60"
          >
            <span className="text-w-dim">{lightMode ? <Moon size={14} /> : <Sun size={14} />}</span>
            <span className="text-w-text">{lightMode ? 'Switch to dark mode' : 'Switch to light mode'}</span>
          </button>
        </div>
      )}
    </div>
  )
}
