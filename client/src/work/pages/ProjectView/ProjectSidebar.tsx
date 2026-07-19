import { Link } from 'react-router-dom'
import { ArrowLeft, Plus, MessageSquare, Mail, Pin, PinOff, Pencil } from 'lucide-react'
import type { MWProject } from '../../types'
import type { ProjectViewModel } from './useProjectView'

interface Props {
  vm: ProjectViewModel
  project: MWProject
  isRecruiting: boolean
}

/** Left sidebar: back link, chat list (or project title for recruiting), inbox + user footer. */
export function ProjectSidebar({ vm, project, isRecruiting }: Props) {
  const {
    base,
    handleNewChat,
    activeChatId,
    setActiveChatId,
    sidebarMode,
    setSidebarMode,
    setMobileMenuOpen,
    renamingChatId,
    setRenamingChatId,
    renameDraft,
    setRenameDraft,
    renameInputRef,
    handleRenameChat,
    handlePinChat,
    setActiveTab,
    me,
  } = vm
  const inboxUnread = vm.inbox.inboxUnread
  const chats = project.chats || []

  return (
    <>
      {/* Top: back + (new chat, non-recruiting only) */}
      <div className="px-3 py-3 flex items-center justify-between shrink-0" style={{ borderBottom: '1px solid var(--color-w-line)' }}>
        <Link to={base} className="text-[var(--color-w-dim)] hover:text-[var(--color-w-text)]">
          <ArrowLeft size={14} />
        </Link>
        {!isRecruiting && (
          <button
            onClick={handleNewChat}
            title="New chat"
            className="p-1 rounded transition-colors text-[var(--color-w-dim)] hover:text-[var(--color-w-accent)]"
          >
            <Plus size={14} />
          </button>
        )}
      </div>

      {/* Project title (recruiting) or Chat list (other) */}
      {isRecruiting ? (
        <div className="flex-1 overflow-y-auto py-2 px-3">
          <p className="text-[10px] uppercase tracking-wider text-[var(--color-w-dim)] mb-1">Project</p>
          <p className="text-xs font-medium text-[var(--color-w-text)] truncate" title={project.title}>{project.title}</p>
        </div>
      ) : (
      <div className="flex-1 overflow-y-auto py-1">
        {[...(chats || [])].sort((a, b) => (b.is_pinned ? 1 : 0) - (a.is_pinned ? 1 : 0)).map((c) => (
          <div
            key={c.id}
            className={`group flex items-center px-3 py-2 transition-colors cursor-pointer ${
              activeChatId === c.id && sidebarMode === 'chats'
                ? 'text-[var(--color-w-text)]'
                : 'text-[var(--color-w-dim)] hover:text-[var(--color-w-text)]'
            }`}
            style={activeChatId === c.id && sidebarMode === 'chats' ? { background: 'var(--color-w-surface2)' } : {}}
            onClick={() => { setActiveChatId(c.id); setSidebarMode('chats'); setMobileMenuOpen(false) }}
          >
            {renamingChatId === c.id ? (
              <input
                ref={renameInputRef}
                value={renameDraft}
                onChange={(e) => setRenameDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleRenameChat(c.id); if (e.key === 'Escape') setRenamingChatId(null) }}
                onBlur={() => handleRenameChat(c.id)}
                autoFocus
                className="flex-1 text-xs bg-transparent border-b border-[var(--color-w-accent)] outline-none text-[var(--color-w-text)] min-w-0"
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <>
                {c.is_pinned && <Pin size={8} className="shrink-0 mr-1 text-[var(--color-w-accent)]" />}
                <MessageSquare size={10} className="shrink-0 mr-1.5" />
                <span className="flex-1 text-xs truncate">{c.title}</span>
                <div className="hidden group-hover:flex items-center gap-0.5 shrink-0 ml-1">
                  <button
                    onClick={(e) => { e.stopPropagation(); setRenamingChatId(c.id); setRenameDraft(c.title) }}
                    className="p-0.5 rounded hover:text-[var(--color-w-accent)]"
                    title="Rename"
                  >
                    <Pencil size={9} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handlePinChat(c.id, c.is_pinned) }}
                    className="p-0.5 rounded hover:text-[var(--color-w-accent)]"
                    title={c.is_pinned ? 'Unpin' : 'Pin'}
                  >
                    {c.is_pinned ? <PinOff size={9} /> : <Pin size={9} />}
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
      )}

      {/* Bottom: Inbox + User */}
      <div style={{ borderTop: '1px solid var(--color-w-line)' }} className="shrink-0">
        <button
          // The inbox pane shares a slot with the AI chat pane, so point the
          // tab at whichever one owns it (vm.aiTab) — sending collab to 'chat'
          // would render the discussion channel and the inbox at once.
          onClick={() => { setSidebarMode(sidebarMode === 'inbox' ? 'chats' : 'inbox'); setActiveTab(vm.aiTab); setMobileMenuOpen(false) }}
          className={`w-full flex items-center gap-1.5 px-3 py-2.5 text-xs transition-colors ${
            sidebarMode === 'inbox' ? 'text-[var(--color-w-text)]' : 'text-[var(--color-w-dim)] hover:text-[var(--color-w-text)]'
          }`}
          style={sidebarMode === 'inbox' ? { background: 'var(--color-w-surface2)' } : {}}
        >
          <Mail size={12} />
          <span className="flex-1 text-left">Inbox</span>
          {inboxUnread > 0 && (
            <span className="w-4 h-4 rounded-full bg-blue-500 text-[8px] font-bold text-white flex items-center justify-center">
              {inboxUnread > 9 ? '9+' : inboxUnread}
            </span>
          )}
        </button>
        <Link
          to="/app/settings"
          className="flex items-center gap-1.5 px-3 py-2.5 text-xs text-[var(--color-w-dim)] hover:text-[var(--color-w-text)] transition-colors"
        >
          {me?.user?.avatar_url ? (
            <img src={me.user.avatar_url} className="w-5 h-5 rounded-full object-cover" alt="" />
          ) : (
            <div className="w-5 h-5 rounded-full bg-w-surface2 flex items-center justify-center text-[8px] font-bold text-w-text">
              {(me?.profile?.name || me?.user?.email || '?')[0].toUpperCase()}
            </div>
          )}
          <span className="truncate">{me?.profile?.name || me?.user?.email || 'Settings'}</span>
        </Link>
      </div>
    </>
  )
}
