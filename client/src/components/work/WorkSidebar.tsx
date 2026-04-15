import { useEffect, useState, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Hash, FolderOpen, MessageSquare, Plus, ChevronDown, PanelLeftClose, Mail, MailOpen, Home, Pencil, LogOut, FileText, Presentation, Users, X, Compass, CreditCard, Sparkles } from 'lucide-react'
import { listChannels, updateChannel, listPendingConnections } from '../../api/channels'
import type { ChannelSummary } from '../../api/channels'
import { listThreads, listProjects, updateTitle, updateProjectMeta, createProjectNew, getMWSubscription, startPersonalCheckout } from '../../api/matchaWork'
import type { MWThread, MWProject } from '../../types/matcha-work'
import { getUnreadCount } from '../../api/inbox'
import { useMe } from '../../hooks/useMe'
import CreateChannelModal from '../channels/CreateChannelModal'
import HiringClientPickerModal from '../matcha-work/HiringClientPickerModal'
import type { RecruitingClient } from '../../types/matcha-work'

interface Props {
  open: boolean
  onToggle: () => void
}

type RenameItem = { type: 'channel' | 'project' | 'thread'; id: string; name: string }

export default function WorkSidebar({ open, onToggle }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const { me, isPersonal } = useMe()
  const canCreateChannel = ['client', 'admin', 'individual'].includes(me?.user?.role ?? '')

  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [projects, setProjects] = useState<MWProject[]>([])
  const [threads, setThreads] = useState<MWThread[]>([])
  const [inboxUnread, setInboxUnread] = useState(0)
  const [pendingConnections, setPendingConnections] = useState(0)
  const [showCreateChannel, setShowCreateChannel] = useState(false)
  const [showProjectTypePicker, setShowProjectTypePicker] = useState(false)
  const [showHiringClientPicker, setShowHiringClientPicker] = useState(false)

  const [channelsOpen, setChannelsOpen] = useState(true)
  const [projectsOpen, setProjectsOpen] = useState(true)
  const [threadsOpen, setThreadsOpen] = useState(false)
  const [plusActive, setPlusActive] = useState<boolean | null>(null)
  const [upgrading, setUpgrading] = useState(false)

  // Inline rename state
  const [renaming, setRenaming] = useState<RenameItem | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const renameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    listChannels().then(setChannels).catch(() => {})
    listProjects().then(setProjects).catch(() => {})
    listThreads('active').then(setThreads).catch(() => {})
    getUnreadCount().then((r) => setInboxUnread(r.count)).catch(() => {})
    listPendingConnections().then((p) => setPendingConnections(p.length)).catch(() => {})
    if (isPersonal) {
      getMWSubscription()
        .then((s) => setPlusActive(
          !!s.active && s.pack_id === 'matcha_work_personal'
        ))
        .catch(() => setPlusActive(false))
    }
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

  async function handleCreateProject(type: 'general' | 'presentation' | 'recruiting' = 'general') {
    setShowProjectTypePicker(false)
    if (type === 'recruiting' && isPersonal) {
      setShowHiringClientPicker(true)
      return
    }
    const titles: Record<string, string> = {
      general: 'New Project',
      presentation: 'New Presentation',
      recruiting: 'New Job Posting',
    }
    try {
      const project = await createProjectNew(titles[type], type)
      setProjects((prev) => [project, ...prev])
      navigate(`/work/projects/${project.id}`)
    } catch {}
  }

  async function handleUpgradeToPlus() {
    if (upgrading) return
    setUpgrading(true)
    try {
      const { checkout_url } = await startPersonalCheckout()
      window.location.href = checkout_url
    } catch {
      setUpgrading(false)
    }
  }

  async function handlePickHiringClient(client: RecruitingClient | null) {
    setShowHiringClientPicker(false)
    try {
      const title = client ? `New role at ${client.name}` : 'New Job Posting'
      const project = await createProjectNew(title, 'recruiting', client?.id ?? null)
      const enriched = { ...project, hiring_client_name: client?.name ?? null }
      setProjects((prev) => [enriched, ...prev])
      navigate(`/work/projects/${project.id}`)
    } catch {}
  }

  function handleLogout() {
    localStorage.removeItem('matcha_access_token')
    localStorage.removeItem('matcha_refresh_token')
    window.location.href = '/login'
  }

  const isActive = (path: string) => location.pathname === path
  const inboxPath = '/work/inbox'
  const totalChannelUnread = channels.reduce((sum, ch) => sum + ch.unread_count, 0)
  const userName = me?.profile?.name || me?.user?.email?.split('@')[0] || 'User'
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
          onClick={() => navigate('/work')}
          className={`p-2 rounded-lg transition-colors ${isActive('/work') ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-white hover:bg-zinc-800/50'}`}
          title="Home"
        >
          <Home size={16} />
        </button>

        <button
          onClick={() => navigate('/work/email')}
          className={`p-2 rounded-lg transition-colors ${isActive('/work/email') ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-white hover:bg-zinc-800/50'}`}
          title="Email"
        >
          <MailOpen size={16} />
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
          onClick={() => navigate('/work/connections')}
          className={`relative p-2 rounded-lg transition-colors ${isActive('/work/connections') ? 'bg-zinc-800 text-white' : 'text-zinc-500 hover:text-white hover:bg-zinc-800/50'}`}
          title="People"
        >
          <Users size={16} />
          {pendingConnections > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-emerald-600 text-[8px] font-bold text-white flex items-center justify-center">
              {pendingConnections > 9 ? '!' : pendingConnections}
            </span>
          )}
        </button>

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

          {/* Email */}
          <button
            onClick={() => navigate('/work/email')}
            className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
              location.pathname === '/work/email'
                ? 'bg-zinc-800/60 text-white font-medium'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30'
            }`}
          >
            <MailOpen size={14} strokeWidth={1.6} />
            Email
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
                  onClick={(e) => { e.stopPropagation(); navigate('/work/channels') }}
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
                      isActive(`/work/channels/${ch.id}`)
                        ? 'bg-zinc-800/60 text-white font-medium'
                        : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30'
                    }`}
                    onClick={() => navigate(`/work/channels/${ch.id}`)}
                  >
                    <Hash size={14} className="text-zinc-500 shrink-0" strokeWidth={1.6} />
                    {ch.is_paid && (
                      <span className="text-[9px] font-bold text-emerald-500 shrink-0">$</span>
                    )}
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

          {/* Projects */}
          <div className="mt-1">
            <button
              onClick={() => setProjectsOpen(!projectsOpen)}
              className="flex items-center justify-between w-full px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-zinc-500 hover:text-zinc-400 transition-colors"
            >
              Projects
              <div className="flex items-center gap-1">
                <span
                  onClick={(e) => { e.stopPropagation(); setShowProjectTypePicker(true) }}
                  className="hover:text-emerald-400 cursor-pointer"
                >
                  <Plus size={12} />
                </span>
                <ChevronDown size={12} className={`transition-transform ${projectsOpen ? '' : '-rotate-90'}`} />
              </div>
            </button>
            {projectsOpen && (
              <div className="space-y-0.5 mt-0.5">
                {projects.length === 0 && (
                  <p className="px-2.5 py-1 text-[11px] text-zinc-600">No projects</p>
                )}
                {(() => {
                  const renderProjectRow = (p: MWProject) => (
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
                  )

                  if (!isPersonal) {
                    return projects.slice(0, 10).map(renderProjectRow)
                  }

                  // Personal: group by hiring client (Unassigned last)
                  const groups = new Map<string, { name: string; items: MWProject[] }>()
                  for (const p of projects) {
                    const key = p.hiring_client_id || '__unassigned'
                    const name = p.hiring_client_name || 'Unassigned'
                    if (!groups.has(key)) groups.set(key, { name, items: [] })
                    groups.get(key)!.items.push(p)
                  }
                  const orderedKeys = Array.from(groups.keys()).sort((a, b) => {
                    if (a === '__unassigned') return 1
                    if (b === '__unassigned') return -1
                    return groups.get(a)!.name.localeCompare(groups.get(b)!.name)
                  })
                  return orderedKeys.map((key) => {
                    const g = groups.get(key)!
                    return (
                      <div key={key}>
                        <p className="px-2.5 pt-1 pb-0.5 text-[10px] uppercase tracking-wider text-zinc-600 truncate">
                          {g.name}
                        </p>
                        {g.items.map(renderProjectRow)}
                      </div>
                    )
                  })
                })()}
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
            {threadsOpen && (() => {
              const myThreads = threads.filter((t) => t.collaborator_count === 0)
              const sharedThreads = threads.filter((t) => t.collaborator_count > 0)

              const renderThread = (t: MWThread) => (
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
              )

              if (threads.length === 0) {
                return <p className="px-2.5 py-1 text-[11px] text-zinc-600">No threads</p>
              }

              return (
                <div className="space-y-0.5 mt-0.5">
                  {myThreads.slice(0, 10).map(renderThread)}
                  {sharedThreads.length > 0 && (
                    <>
                      <p className="px-2.5 pt-2 pb-0.5 text-[10px] uppercase tracking-wider text-zinc-600 flex items-center gap-1">
                        <Users size={10} />
                        Shared
                      </p>
                      {sharedThreads.slice(0, 10).map(renderThread)}
                    </>
                  )}
                </div>
              )
            })()}
          </div>
        </nav>

        {/* Footer: Inbox + User profile + Logout */}
        <div className="px-2 py-2 border-t border-zinc-800/30 space-y-1">
          {isPersonal && plusActive === false && (
            <button
              onClick={handleUpgradeToPlus}
              disabled={upgrading}
              className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] text-amber-400 hover:text-amber-300 hover:bg-amber-500/10 transition-colors disabled:opacity-50"
            >
              <Sparkles size={14} strokeWidth={1.8} />
              {upgrading ? 'Opening checkout…' : 'Upgrade to Plus'}
            </button>
          )}
          {isPersonal && plusActive === true && (
            <div className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] text-amber-400/80">
              <Sparkles size={14} strokeWidth={1.8} />
              Plus active
            </div>
          )}
          <button
            onClick={() => navigate('/work/billing')}
            className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30 transition-colors"
          >
            <CreditCard size={14} strokeWidth={1.6} />
            Billing
          </button>
          <button
            onClick={() => navigate('/work/connections')}
            className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
              isActive('/work/connections')
                ? 'bg-zinc-800/60 text-white font-medium'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/30'
            }`}
          >
            <Users size={14} strokeWidth={1.6} />
            People
            {pendingConnections > 0 && (
              <span className="ml-auto w-4 h-4 rounded-full bg-emerald-600 text-[9px] font-bold text-white flex items-center justify-center shrink-0">
                {pendingConnections > 9 ? '!' : pendingConnections}
              </span>
            )}
          </button>
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

          {/* User profile */}
          <div className="flex items-center gap-2 px-2.5 py-2 mt-1">
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
          canCreatePaid={me?.user?.role === 'individual' || me?.user?.role === 'admin'}
          onCreated={(ch) => {
            setShowCreateChannel(false)
            setChannels((prev) => [{ ...ch, member_count: 1, unread_count: 0, last_message_at: null, last_message_preview: null, is_member: true } as ChannelSummary, ...prev])
            navigate(`/work/channels/${ch.id}`)
          }}
        />
      )}

      {showProjectTypePicker && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowProjectTypePicker(false)}>
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white font-semibold">New Project</h2>
              <button onClick={() => setShowProjectTypePicker(false)} className="text-zinc-500 hover:text-white">
                <X size={16} />
              </button>
            </div>
            <p className="text-zinc-400 text-sm mb-4">What kind of project?</p>
            <div className="space-y-2">
              {([
                { type: 'general' as const, icon: FileText, label: 'Research / Report', desc: 'Build documents and plans from chat' },
                { type: 'presentation' as const, icon: Presentation, label: 'Presentation', desc: 'Create slide decks and pitch materials' },
                { type: 'recruiting' as const, icon: Users, label: 'Job Posting', desc: 'Recruiting pipeline with resumes and interviews' },
              ]).map((opt) => (
                <button
                  key={opt.type}
                  onClick={() => handleCreateProject(opt.type)}
                  className="w-full flex items-center gap-3 p-3 rounded-lg border border-zinc-700 hover:border-emerald-600 hover:bg-zinc-800/50 transition-colors text-left"
                >
                  <opt.icon size={20} className="text-emerald-500 shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-white">{opt.label}</p>
                    <p className="text-xs text-zinc-400">{opt.desc}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {showHiringClientPicker && (
        <HiringClientPickerModal
          onClose={() => setShowHiringClientPicker(false)}
          onPicked={handlePickHiringClient}
        />
      )}
    </>
  )
}
