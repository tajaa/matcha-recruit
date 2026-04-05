import { useEffect, useState, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Hash, FolderOpen, MessageSquare, Plus, ChevronDown, PanelLeftClose, Mail, Home, Pencil } from 'lucide-react'
import { listChannels, updateChannel } from '../../api/channels'
import type { ChannelSummary } from '../../api/channels'
import { listThreads, listProjects, updateTitle, updateProjectMeta } from '../../api/matchaWork'
import type { MWThread, MWProject } from '../../types/matcha-work'
import { getUnreadCount } from '../../api/inbox'
import { useMe } from '../../hooks/useMe'
import CreateChannelModal from '../channels/CreateChannelModal'

interface Props {
  open: boolean
  onToggle: () => void
}

type RenameItem = { type: 'channel' | 'project' | 'thread'; id: string; name: string }

export default function WorkSidebar({ open, onToggle }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const { me } = useMe()
  const canCreateChannel = ['client', 'admin', 'individual'].includes(me?.user?.role ?? '')

  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [projects, setProjects] = useState<MWProject[]>([])
  const [threads, setThreads] = useState<MWThread[]>([])
  const [inboxUnread, setInboxUnread] = useState(0)
  const [showCreateChannel, setShowCreateChannel] = useState(false)

  const [channelsOpen, setChannelsOpen] = useState(true)
  const [projectsOpen, setProjectsOpen] = useState(true)
  const [threadsOpen, setThreadsOpen] = useState(false)

  // Inline rename state
  const [renaming, setRenaming] = useState<RenameItem | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const renameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listChannels().then(setChannels).catch(() => {})
    listProjects().then(setProjects).catch(() => {})
    listThreads('active').then(setThreads).catch(() => {})
    getUnreadCount().then((r) => setInboxUnread(r.count)).catch(() => {})
  }, [])

  useEffect(() => {
    if (location.pathname === '/work') {
      listChannels().then(setChannels).catch(() => {})
    }
  }, [location.pathname])

  // Poll inbox unread
  useEffect(() => {
    const id = setInterval(() => {
      getUnreadCount().then((r) => setInboxUnread(r.count)).catch(() => {})
    }, 60_000)
    return () => clearInterval(id)
  }, [])

  // Focus rename input when it appears
  useEffect(() => {
    if (renaming) renameRef.current?.focus()
  }, [renaming])

  function startRename(type: RenameItem['type'], id: string, name: string) {
    setRenaming({ type: type!, id, name })
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
        setChannels((prev) => prev.map((ch) => ch.id === renaming.id ? { ...ch, name: newName, slug: newName.toLowerCase().replace(/[^a-z0-9]+/g, '-') } : ch))
      } else if (renaming.type === 'project') {
        await updateProjectMeta(renaming.id, { title: newName })
        setProjects((prev) => prev.map((p) => p.id === renaming.id ? { ...p, title: newName } : p))
      } else if (renaming.type === 'thread') {
        await updateTitle(renaming.id, newName)
        setThreads((prev) => prev.map((t) => t.id === renaming.id ? { ...t, title: newName } : t))
      }
    } catch {}
    setRenaming(null)
  }

  const isActive = (path: string) => location.pathname === path
  const inboxPath = '/work/inbox'
  const totalChannelUnread = channels.reduce((sum, ch) => sum + ch.unread_count, 0)

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
          onClick={() => navigate('/work')}
          className={`p-2 rounded-lg transition-colors ${isActive('/work') ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-white hover:bg-zinc-800/50'}`}
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
          onClick={() => { onToggle(); setProjectsOpen(true) }}
          className={`p-2 rounded-lg transition-colors ${location.pathname.includes('/projects/') ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-white hover:bg-zinc-800/50'}`}
          title="Projects"
        >
          <FolderOpen size={16} />
        </button>

        <button
          onClick={() => { onToggle(); setThreadsOpen(true) }}
          className={`p-2 rounded-lg transition-colors ${location.pathname.match(/\/work\/[^/]+$/) && !location.pathname.includes('/channels/') && !location.pathname.includes('/projects/') && location.pathname !== '/work' ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-white hover:bg-zinc-800/50'}`}
          title="Threads"
        >
          <MessageSquare size={16} />
        </button>

        <div className="flex-1" />

        <button
          onClick={() => navigate(inboxPath)}
          className={`relative p-2 rounded-lg transition-colors text-zinc-500 hover:text-white hover:bg-zinc-800/50`}
          title="Inbox"
        >
          <Mail size={16} />
          {inboxUnread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-blue-500 text-[8px] font-bold text-white flex items-center justify-center">
              {inboxUnread > 9 ? '!' : inboxUnread}
            </span>
          )}
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
        {/* Header */}
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
            onClick={() => navigate('/work')}
            className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
              location.pathname === '/work'
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
                    className={`group w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                      isActive(`/work/channels/${ch.id}`)
                        ? 'bg-zinc-800/60 text-white font-medium'
                        : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30'
                    }`}
                  >
                    <Hash size={14} className="text-zinc-500 shrink-0" strokeWidth={1.6} />
                    {renaming?.type === 'channel' && renaming.id === ch.id ? (
                      renderRenameInput()
                    ) : (
                      <>
                        <button
                          onClick={() => navigate(`/work/channels/${ch.id}`)}
                          className="flex-1 min-w-0 text-left truncate"
                        >
                          {ch.name}
                        </button>
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

          {/* Projects */}
          <div className="mt-1">
            <button
              onClick={() => setProjectsOpen(!projectsOpen)}
              className="flex items-center justify-between w-full px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-zinc-500 hover:text-zinc-400 transition-colors"
            >
              Projects
              <ChevronDown size={12} className={`transition-transform ${projectsOpen ? '' : '-rotate-90'}`} />
            </button>
            {projectsOpen && (
              <div className="space-y-0.5 mt-0.5">
                {projects.length === 0 && (
                  <p className="px-2.5 py-1 text-[11px] text-zinc-600">No projects</p>
                )}
                {projects.slice(0, 10).map((p) => (
                  <div
                    key={p.id}
                    className={`group w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                      isActive(`/work/projects/${p.id}`)
                        ? 'bg-zinc-800/60 text-white font-medium'
                        : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30'
                    }`}
                  >
                    <FolderOpen size={14} className="text-[#ce9178] shrink-0" strokeWidth={1.6} />
                    {renaming?.type === 'project' && renaming.id === p.id ? (
                      renderRenameInput()
                    ) : (
                      <>
                        <button
                          onClick={() => navigate(`/work/projects/${p.id}`)}
                          className="flex-1 min-w-0 text-left truncate"
                        >
                          {p.title}
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); startRename('project', p.id, p.title) }}
                          className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 text-zinc-500 hover:text-zinc-300 transition-all"
                          title="Rename"
                        >
                          <Pencil size={11} />
                        </button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Threads */}
          <div className="mt-1">
            <button
              onClick={() => setThreadsOpen(!threadsOpen)}
              className="flex items-center justify-between w-full px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-zinc-500 hover:text-zinc-400 transition-colors"
            >
              Threads
              <ChevronDown size={12} className={`transition-transform ${threadsOpen ? '' : '-rotate-90'}`} />
            </button>
            {threadsOpen && (
              <div className="space-y-0.5 mt-0.5">
                {threads.length === 0 && (
                  <p className="px-2.5 py-1 text-[11px] text-zinc-600">No threads</p>
                )}
                {threads.slice(0, 10).map((t) => (
                  <div
                    key={t.id}
                    className={`group w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                      isActive(`/work/${t.id}`)
                        ? 'bg-zinc-800/60 text-white font-medium'
                        : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30'
                    }`}
                  >
                    <MessageSquare size={14} className="text-zinc-500 shrink-0" strokeWidth={1.6} />
                    {renaming?.type === 'thread' && renaming.id === t.id ? (
                      renderRenameInput()
                    ) : (
                      <>
                        <button
                          onClick={() => navigate(`/work/${t.id}`)}
                          className="flex-1 min-w-0 text-left truncate"
                        >
                          {t.title}
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); startRename('thread', t.id, t.title) }}
                          className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 text-zinc-500 hover:text-zinc-300 transition-all"
                          title="Rename"
                        >
                          <Pencil size={11} />
                        </button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </nav>

        {/* Inbox footer */}
        <div className="px-2 py-2 border-t border-zinc-800/30">
          <button
            onClick={() => navigate(inboxPath)}
            className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30 transition-colors"
          >
            <Mail size={14} strokeWidth={1.6} />
            Inbox
            {inboxUnread > 0 && (
              <span className="ml-auto w-4 h-4 rounded-full bg-blue-500 text-[9px] font-bold text-white flex items-center justify-center shrink-0">
                {inboxUnread > 9 ? '!' : inboxUnread}
              </span>
            )}
          </button>
        </div>
      </aside>

      {showCreateChannel && (
        <CreateChannelModal
          onClose={() => setShowCreateChannel(false)}
          onCreated={(ch) => {
            setShowCreateChannel(false)
            setChannels((prev) => [{ ...ch, member_count: 1, unread_count: 0, last_message_at: null, last_message_preview: null, is_member: true } as ChannelSummary, ...prev])
            navigate(`/work/channels/${ch.id}`)
          }}
        />
      )}
    </>
  )
}
