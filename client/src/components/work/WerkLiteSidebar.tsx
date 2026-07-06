import { useEffect, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Hash, LayoutGrid, Plus, ChevronDown, PanelLeftClose, Home, Pencil, LogOut, Compass } from 'lucide-react'
import { listChannels, updateChannel, CHANNELS_CHANGED_EVENT } from '../../api/channels'
import type { ChannelSummary } from '../../api/channels'
import { disconnectSharedChannelSocket } from '../../api/channelSocket'
import { resetAuthCaches } from '../../api/authReset'
import { listProjects, createProjectNew, updateProjectMeta } from '../../api/matchaWork'
import type { MWProject } from '../../types/matcha-work'
import { useMe } from '../../hooks/useMe'
import CreateChannelModal from '../channels/CreateChannelModal'
import { useWorkBase } from '../../routes/WorkSurfaceContext'

interface Props {
  open: boolean
  onToggle: () => void
}

type RenameItem = { type: 'channel' | 'board'; id: string; name: string }

// Slim sidebar for the werk-lite business work-chat surface: Channels + Boards
// only. A "Board" is a matcha-work project under the hood. Deliberately a
// separate component from WorkSidebar (which is tangled with personal/beta/
// recruiting gating that werk-lite doesn't want).
export default function WerkLiteSidebar({ open, onToggle }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const base = useWorkBase()
  const { me } = useMe()
  const canCreateChannel = ['client', 'admin', 'individual'].includes(me?.user?.role ?? '')

  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [boards, setBoards] = useState<MWProject[]>([])
  const [showCreateChannel, setShowCreateChannel] = useState(false)
  const [creatingBoard, setCreatingBoard] = useState(false)
  const [channelsOpen, setChannelsOpen] = useState(true)
  const [boardsOpen, setBoardsOpen] = useState(true)

  const [renaming, setRenaming] = useState<RenameItem | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const renameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listChannels().then(setChannels).catch(() => {})
    // Boards = general kanban projects only — never surface recruiting/
    // presentation/discipline projects (also mw_projects) in the chat product.
    listProjects().then((p) => setBoards(p.filter((b) => b.project_type === 'general'))).catch(() => {})
  }, [])

  // Refetch channels when anywhere in the app creates/joins/leaves one.
  useEffect(() => {
    const handler = () => { listChannels().then(setChannels).catch(() => {}) }
    window.addEventListener(CHANNELS_CHANGED_EVENT, handler)
    return () => window.removeEventListener(CHANNELS_CHANGED_EVENT, handler)
  }, [])

  useEffect(() => {
    if (renaming) renameRef.current?.focus()
  }, [renaming])

  function startRename(type: RenameItem['type'], id: string, name: string) {
    setRenaming({ type, id, name })
    setRenameDraft(name)
  }

  async function submitRename() {
    if (!renaming || !renameDraft.trim() || renameDraft.trim() === renaming.name) {
      setRenaming(null)
      return
    }
    const newName = renameDraft.trim()
    try {
      if (renaming.type === 'channel') {
        await updateChannel(renaming.id, { name: newName })
        setChannels((prev) => prev.map((ch) => ch.id === renaming.id
          ? { ...ch, name: newName, slug: newName.toLowerCase().replace(/[^a-z0-9]+/g, '-') }
          : ch))
      } else {
        await updateProjectMeta(renaming.id, { title: newName })
        setBoards((prev) => prev.map((b) => b.id === renaming.id ? { ...b, title: newName } : b))
      }
    } catch { /* keep prior name on failure */ }
    setRenaming(null)
  }

  async function handleCreateBoard() {
    if (creatingBoard) return
    setCreatingBoard(true)
    try {
      const board = await createProjectNew('New Board', 'general')
      setBoards((prev) => [board, ...prev])
      navigate(`${base}/boards/${board.id}`)
    } catch { /* surfaced by the API error reporter */ } finally {
      setCreatingBoard(false)
    }
  }

  function handleLogout() {
    localStorage.removeItem('matcha_access_token')
    localStorage.removeItem('matcha_refresh_token')
    resetAuthCaches()
    disconnectSharedChannelSocket()
    window.location.href = '/login'
  }

  const isActive = (path: string) => location.pathname === path
  const totalChannelUnread = channels.reduce((sum, ch) => sum + ch.unread_count, 0)
  const userName = me?.profile?.company_name || me?.profile?.name || me?.user?.email?.split('@')[0] || 'User'
  const userEmail = me?.user?.email || ''
  const userAvatar = me?.user?.avatar_url

  // ─── Collapsed: icon rail ───
  if (!open) {
    return (
      <aside className="w-12 bg-[#0c0c0e] border-r border-zinc-800/30 flex flex-col items-center py-2 gap-1 shrink-0">
        <button
          onClick={onToggle}
          className="p-2 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-white transition-colors mb-1"
          title="Open sidebar"
        >
          <PanelLeftClose size={16} className="rotate-180" />
        </button>
        <div className="w-6 border-t border-zinc-800/40 mb-1" />
        <button
          onClick={() => navigate(base)}
          className={`p-2 rounded-lg transition-colors ${isActive(base) ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-white hover:bg-zinc-800/50'}`}
          title="Home"
        >
          <Home size={16} />
        </button>
        <button
          onClick={() => { onToggle(); setChannelsOpen(true) }}
          className={`relative p-2 rounded-lg transition-colors ${location.pathname.includes('/channels/') ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-white hover:bg-zinc-800/50'}`}
          title="Channels"
        >
          <Hash size={16} />
          {totalChannelUnread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-emerald-600 text-[8px] font-bold text-white flex items-center justify-center">
              {totalChannelUnread > 9 ? '!' : totalChannelUnread}
            </span>
          )}
        </button>
        <button
          onClick={() => { onToggle(); setBoardsOpen(true) }}
          className={`p-2 rounded-lg transition-colors ${location.pathname.includes('/boards/') ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-white hover:bg-zinc-800/50'}`}
          title="Boards"
        >
          <LayoutGrid size={16} />
        </button>
      </aside>
    )
  }

  // ─── Inline rename input ───
  function renderRenameInput() {
    return (
      <div className="flex items-center gap-1 px-1 flex-1 min-w-0">
        <input
          ref={renameRef}
          value={renameDraft}
          onChange={(e) => setRenameDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submitRename()
            if (e.key === 'Escape') setRenaming(null)
          }}
          onBlur={submitRename}
          className="flex-1 min-w-0 rounded border border-zinc-600 bg-zinc-800 px-1.5 py-0.5 text-[13px] text-zinc-100 outline-none focus:border-emerald-600"
        />
      </div>
    )
  }

  // ─── Expanded sidebar ───
  return (
    <>
      <aside className="w-56 bg-[#0c0c0e] border-r border-zinc-800/30 flex flex-col shrink-0 overflow-hidden">
        <div className="flex items-center justify-between px-3 py-3">
          <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Workspace</span>
          <button
            onClick={onToggle}
            className="p-1 rounded hover:bg-zinc-800 text-zinc-500 hover:text-white transition-colors"
            title="Collapse sidebar"
          >
            <PanelLeftClose size={16} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 space-y-1 pb-3">
          {/* Home */}
          <button
            onClick={() => navigate(base)}
            className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
              location.pathname === base
                ? 'bg-zinc-800/60 text-white font-medium'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30'
            }`}
          >
            <Home size={14} strokeWidth={1.6} />
            Home
          </button>

          {/* Channels */}
          <div className="mt-2">
            <button
              onClick={() => setChannelsOpen(!channelsOpen)}
              className="flex items-center justify-between w-full px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-zinc-500 hover:text-zinc-400 transition-colors"
            >
              Channels
              <div className="flex items-center gap-1">
                <span
                  onClick={(e) => { e.stopPropagation(); navigate(`${base}/channels`) }}
                  className="hover:text-emerald-400 cursor-pointer"
                  title="Browse channels"
                >
                  <Compass size={12} />
                </span>
                {canCreateChannel && (
                  <span
                    onClick={(e) => { e.stopPropagation(); setShowCreateChannel(true) }}
                    className="hover:text-emerald-400 cursor-pointer"
                  >
                    <Plus size={12} />
                  </span>
                )}
                <ChevronDown size={12} className={`transition-transform ${channelsOpen ? '' : '-rotate-90'}`} />
              </div>
            </button>
            {channelsOpen && (
              <div className="space-y-0.5 mt-0.5">
                {channels.length === 0 && (
                  <p className="px-2.5 py-1 text-[11px] text-zinc-600">No channels</p>
                )}
                {channels.map((ch) => (
                  <div
                    key={ch.id}
                    className={`group w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors cursor-pointer ${
                      isActive(`${base}/channels/${ch.id}`)
                        ? 'bg-zinc-800/60 text-white font-medium'
                        : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30'
                    }`}
                    onClick={() => navigate(`${base}/channels/${ch.id}`)}
                  >
                    <Hash size={14} className="text-zinc-500 shrink-0" strokeWidth={1.6} />
                    {renaming?.type === 'channel' && renaming.id === ch.id ? (
                      renderRenameInput()
                    ) : (
                      <>
                        <span className={`flex-1 min-w-0 truncate ${ch.unread_count > 0 ? 'font-semibold text-white' : ''}`}>
                          {ch.name}
                        </span>
                        <button
                          onClick={(e) => { e.stopPropagation(); startRename('channel', ch.id, ch.name) }}
                          className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 text-zinc-500 hover:text-zinc-300 transition-all"
                          title="Rename"
                        >
                          <Pencil size={11} />
                        </button>
                      </>
                    )}
                    {ch.unread_count > 0 && !renaming && (
                      <span className="ml-auto w-4 h-4 rounded-full bg-emerald-600 text-[9px] font-bold text-white flex items-center justify-center shrink-0">
                        {ch.unread_count > 9 ? '9+' : ch.unread_count}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Boards */}
          <div className="mt-1">
            <button
              onClick={() => setBoardsOpen(!boardsOpen)}
              className="flex items-center justify-between w-full px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-zinc-500 hover:text-zinc-400 transition-colors"
            >
              Boards
              <div className="flex items-center gap-1">
                {canCreateChannel && (
                  <span
                    onClick={(e) => { e.stopPropagation(); handleCreateBoard() }}
                    className="hover:text-emerald-400 cursor-pointer"
                    title="New board"
                  >
                    <Plus size={12} />
                  </span>
                )}
                <ChevronDown size={12} className={`transition-transform ${boardsOpen ? '' : '-rotate-90'}`} />
              </div>
            </button>
            {boardsOpen && (
              <div className="space-y-0.5 mt-0.5">
                {boards.length === 0 && (
                  <p className="px-2.5 py-1 text-[11px] text-zinc-600">No boards</p>
                )}
                {boards.slice(0, 30).map((b) => (
                  <div
                    key={b.id}
                    className={`group w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                      isActive(`${base}/boards/${b.id}`)
                        ? 'bg-zinc-800/60 text-white font-medium'
                        : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30'
                    }`}
                  >
                    <LayoutGrid size={14} className="text-[#ce9178] shrink-0" strokeWidth={1.6} />
                    {renaming?.type === 'board' && renaming.id === b.id ? (
                      renderRenameInput()
                    ) : (
                      <>
                        <button
                          onClick={() => navigate(`${base}/boards/${b.id}`)}
                          className="flex-1 min-w-0 text-left truncate"
                        >
                          {b.title}
                        </button>
                        {canCreateChannel && (
                          <button
                            onClick={(e) => { e.stopPropagation(); startRename('board', b.id, b.title) }}
                            className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 text-zinc-500 hover:text-zinc-300 transition-all"
                            title="Rename"
                          >
                            <Pencil size={11} />
                          </button>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </nav>

        {/* Footer: company/user + logout */}
        <div className="px-2 py-2 border-t border-zinc-800/30">
          <div className="flex items-center gap-2 px-2.5 py-2">
            {userAvatar ? (
              <img src={userAvatar} alt={userName} className="w-7 h-7 rounded-full object-cover shrink-0" />
            ) : (
              <div className="w-7 h-7 rounded-full bg-zinc-800 flex items-center justify-center text-[11px] font-medium text-zinc-400 shrink-0">
                {userName.charAt(0).toUpperCase()}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-[12px] text-zinc-300 truncate">{userName}</p>
              <p className="text-[10px] text-zinc-600 truncate">{userEmail}</p>
            </div>
            <button
              onClick={handleLogout}
              className="shrink-0 p-1 rounded text-zinc-600 hover:text-red-400 hover:bg-zinc-800/50 transition-colors"
              title="Log out"
            >
              <LogOut size={13} />
            </button>
          </div>
        </div>
      </aside>

      {showCreateChannel && (
        <CreateChannelModal
          onClose={() => setShowCreateChannel(false)}
          canCreatePaid={me?.user?.role === 'admin'}
          onCreated={(ch) => {
            setShowCreateChannel(false)
            setChannels((prev) => [{ ...ch, member_count: 1, unread_count: 0, last_message_at: null, last_message_preview: null, is_member: true } as ChannelSummary, ...prev])
            navigate(`${base}/channels/${ch.id}`)
          }}
        />
      )}
    </>
  )
}
