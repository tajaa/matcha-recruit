import { useEffect, useState, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Hash, FolderOpen, MessageSquare, Plus, ChevronDown, PanelLeftClose, Mail, MailOpen, Home, Pencil, LogOut, FileText, Presentation, Users, X, Compass, CreditCard, Sparkles, Search } from 'lucide-react'
import { listChannels, updateChannel, listPendingConnections, CHANNELS_CHANGED_EVENT } from '../../api/channels'
import { disconnectSharedChannelSocket } from '../../api/channelSocket'
import { resetAuthCaches } from '../../../api/authReset'
import type { ChannelSummary } from '../../api/channels'
import { listThreads, listProjects, updateTitle, updateProjectMeta, createProjectNew, getMWSubscription, startPersonalCheckout } from '../../api/matchaWork'
import type { MWThread, MWProject } from '../../types'
import { getUnreadCount } from '../../api/inbox'
import { useMe } from '../../../hooks/useMe'
import CreateChannelModal from '../channels/CreateChannelModal'
import HiringClientPickerModal from '../panels/HiringClientPickerModal'
import TemplatePickerModal from '../panels/TemplatePickerModal'
import type { RecruitingClient } from '../../types'
import { useWorkBase, useWorkBrand } from '../../routes/WorkSurfaceContext'

/** Sidebar "TABS" strip — the browser-tab-like strip of recently opened items
 *  desktop Werk keeps in `WorkTabsSidebarSection`. Persisted per work surface so
 *  /work and /werk don't bleed into each other. */
type OpenTab = { type: 'channel' | 'project' | 'thread'; id: string; label: string }
const MAX_OPEN_TABS = 6

interface Props {
  open: boolean
  onToggle: () => void
}

type RenameItem = { type: 'channel' | 'project' | 'thread'; id: string; name: string }

export default function WorkSidebar({ open, onToggle }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const base = useWorkBase()
  const brand = useWorkBrand()
  const { me, isPersonal, mwBetaLite } = useMe()
  const canCreateChannel = ['client', 'admin', 'individual'].includes(me?.user?.role ?? '')

  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [projects, setProjects] = useState<MWProject[]>([])
  const [threads, setThreads] = useState<MWThread[]>([])
  const [inboxUnread, setInboxUnread] = useState(0)
  const [pendingConnections, setPendingConnections] = useState(0)
  const [showCreateChannel, setShowCreateChannel] = useState(false)
  const [showProjectTypePicker, setShowProjectTypePicker] = useState(false)
  const [showHiringClientPicker, setShowHiringClientPicker] = useState(false)
  const [showTemplatePicker, setShowTemplatePicker] = useState(false)

  const [channelsOpen, setChannelsOpen] = useState(false)
  const [projectsOpen, setProjectsOpen] = useState(false)
  const [threadsOpen, setThreadsOpen] = useState(false)
  const [plusActive, setPlusActive] = useState<boolean | null>(null)
  const [upgrading, setUpgrading] = useState(false)
  const [filter, setFilter] = useState('')

  const tabsKey = `mw-open-tabs:${base}`
  const [openTabs, setOpenTabs] = useState<OpenTab[]>(() => {
    // Validate shape, not just JSON syntax: a valid-but-wrong value (`{}`, a
    // string, entries missing `type`) would otherwise survive parse and then
    // blow up in `prev.filter` / `tabIcon[t.type]` on the next navigation.
    try {
      const raw: unknown = JSON.parse(localStorage.getItem(tabsKey) || '[]')
      if (!Array.isArray(raw)) return []
      return raw.filter(
        (t): t is OpenTab =>
          !!t &&
          typeof t === 'object' &&
          typeof (t as OpenTab).id === 'string' &&
          typeof (t as OpenTab).label === 'string' &&
          ['channel', 'project', 'thread'].includes((t as OpenTab).type),
      )
    } catch {
      return []
    }
  })

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
    if (location.pathname === base) {
      listChannels().then(setChannels).catch(() => {})
    }
  }, [location.pathname])

  // Refetch channels when anywhere in the app creates/joins/leaves one.
  useEffect(() => {
    const handler = () => {
      listChannels().then(setChannels).catch(() => {})
    }
    window.addEventListener(CHANNELS_CHANGED_EVENT, handler)
    return () => window.removeEventListener(CHANNELS_CHANGED_EVENT, handler)
  }, [])

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

  // Track the currently-open channel/project/thread into the TABS strip —
  // upsert-to-front, capped, persisted per work surface. Only fires once the
  // matching list has loaded so the label is real, not a placeholder.
  useEffect(() => {
    const path = location.pathname
    let entry: OpenTab | null = null
    const channelMatch = path.match(new RegExp(`^${base}/channels/([^/]+)$`))
    const projectMatch = path.match(new RegExp(`^${base}/projects/([^/]+)$`))
    const threadMatch = path.match(new RegExp(`^${base}/([^/]+)$`))
    if (channelMatch) {
      const ch = channels.find((c) => c.id === channelMatch[1])
      if (ch) entry = { type: 'channel', id: ch.id, label: ch.name }
    } else if (projectMatch) {
      const p = projects.find((x) => x.id === projectMatch[1])
      if (p) entry = { type: 'project', id: p.id, label: p.title }
    } else if (threadMatch && threadMatch[1] !== 'email' && threadMatch[1] !== 'inbox' && threadMatch[1] !== 'connections' && threadMatch[1] !== 'billing' && threadMatch[1] !== 'channels') {
      const t = threads.find((x) => x.id === threadMatch[1])
      if (t) entry = { type: 'thread', id: t.id, label: t.title }
    }
    setOpenTabs((prev) => {
      // Re-label stored tabs from the freshly loaded lists, so renaming an item
      // that isn't the currently-open one doesn't strand a stale label forever.
      const relabelled = prev.map((t) => {
        const src =
          t.type === 'channel' ? channels.find((c) => c.id === t.id)?.name
          : t.type === 'project' ? projects.find((p) => p.id === t.id)?.title
          : threads.find((x) => x.id === t.id)?.title
        return src && src !== t.label ? { ...t, label: src } : t
      })
      const next = entry
        ? [entry, ...relabelled.filter((t) => !(t.type === entry!.type && t.id === entry!.id))].slice(0, MAX_OPEN_TABS)
        : relabelled
      // Bail out when nothing actually changed — this effect re-runs on every
      // list refetch (channel create/join, home navigation), and writing an
      // identical array would re-render the sidebar and hit localStorage each time.
      const same =
        next.length === prev.length &&
        next.every((t, i) => t.type === prev[i].type && t.id === prev[i].id && t.label === prev[i].label)
      if (same) return prev
      try {
        localStorage.setItem(tabsKey, JSON.stringify(next))
      } catch {}
      return next
    })
  }, [location.pathname, channels, projects, threads])

  function closeTab(e: React.MouseEvent, tab: OpenTab) {
    e.stopPropagation()
    setOpenTabs((prev) => {
      const next = prev.filter((t) => !(t.type === tab.type && t.id === tab.id))
      try {
        localStorage.setItem(tabsKey, JSON.stringify(next))
      } catch {}
      return next
    })
  }

  function openTabPath(tab: OpenTab): string {
    if (tab.type === 'channel') return `${base}/channels/${tab.id}`
    if (tab.type === 'project') return `${base}/projects/${tab.id}`
    return `${base}/${tab.id}`
  }

  const tabIcon = { channel: Hash, project: FolderOpen, thread: MessageSquare } as const

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
    // For general projects, offer the user a starter template (Proposal,
    // Project Brief, Status Report, Pitch Deck) before creating. Other types
    // have their own structured flow and skip the picker.
    if (type === 'general') {
      setShowTemplatePicker(true)
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
      navigate(`${base}/projects/${project.id}`)
    } catch {}
  }

  async function handlePickTemplate(templateId: string | null) {
    // Title hint mirrors the template name so the user lands in a project
    // they can recognize (rather than yet-another "New Project N").
    const titleByTemplate: Record<string, string> = {
      proposal: 'New Proposal',
      project_brief: 'New Project Brief',
      status_report: 'New Status Report',
      pitch_deck: 'New Pitch Deck',
    }
    const title = templateId ? (titleByTemplate[templateId] ?? 'New Project') : 'New Project'
    try {
      const project = await createProjectNew(title, 'general', null, templateId)
      setProjects((prev) => [project, ...prev])
      navigate(`${base}/projects/${project.id}`)
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
      navigate(`${base}/projects/${project.id}`)
    } catch {}
  }

  function handleLogout() {
    localStorage.removeItem('matcha_access_token')
    localStorage.removeItem('matcha_refresh_token')
    resetAuthCaches()
    disconnectSharedChannelSocket()
    window.location.href = '/login'
  }

  const isActive = (path: string) => location.pathname === path
  const inboxPath = `${base}/inbox`
  const totalChannelUnread = channels.reduce((sum, ch) => sum + ch.unread_count, 0)
  const userName = me?.profile?.name || me?.user?.email?.split('@')[0] || 'User'
  const userEmail = me?.user?.email || ''
  const userAvatar = me?.user?.avatar_url

  // ─── Collapsed: icon rail ───
  if (!open) {
    return (
      <aside className="w-12 bg-w-surface border-r border-w-line flex flex-col items-center py-2 gap-1 shrink-0">
        <button
          onClick={onToggle}
          className="p-2 rounded-lg hover:bg-w-surface2 text-w-dim hover:text-white transition-colors mb-1"
          title="Open sidebar"
        >
          <PanelLeftClose size={16} className="rotate-180" />
        </button>
        <div className="w-6 border-t border-w-line/40 mb-1" />

        <button
          onClick={() => navigate(base)}
          className={`p-2 rounded-lg transition-colors ${isActive(base) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
          title="Home"
        >
          <Home size={16} />
        </button>

        <button
          onClick={() => navigate(`${base}/email`)}
          className={`p-2 rounded-lg transition-colors ${isActive(`${base}/email`) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
          title="Email"
        >
          <MailOpen size={16} />
        </button>

        <button
          onClick={() => { onToggle(); setChannelsOpen(true) }}
          className={`relative p-2 rounded-lg transition-colors ${location.pathname.includes('/channels/') ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
          title="Channels"
        >
          <Hash size={16} />
          {totalChannelUnread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-w-accent text-[8px] font-bold text-white flex items-center justify-center">
              {totalChannelUnread > 9 ? '!' : totalChannelUnread}
            </span>
          )}
        </button>

        {mwBetaLite && (
          <button
            onClick={() => { onToggle(); setProjectsOpen(true) }}
            className={`p-2 rounded-lg transition-colors ${location.pathname.includes('/projects/') ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
            title="Projects"
          >
            <FolderOpen size={16} />
          </button>
        )}

        <button
          onClick={() => { onToggle(); setThreadsOpen(true) }}
          className={`p-2 rounded-lg transition-colors ${new RegExp(`^${base}/[^/]+$`).test(location.pathname) && !location.pathname.includes('/channels/') && !location.pathname.includes('/projects/') ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
          title="Threads"
        >
          <MessageSquare size={16} />
        </button>

        <div className="flex-1" />

        <button
          onClick={() => navigate(`${base}/connections`)}
          className={`relative p-2 rounded-lg transition-colors ${isActive(`${base}/connections`) ? 'bg-w-surface2 text-white' : 'text-w-dim hover:text-white hover:bg-w-surface2/60'}`}
          title="People"
        >
          <Users size={16} />
          {pendingConnections > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-w-accent text-[8px] font-bold text-white flex items-center justify-center">
              {pendingConnections > 9 ? '!' : pendingConnections}
            </span>
          )}
        </button>

        <button
          onClick={() => navigate(inboxPath)}
          className={`relative p-2 rounded-lg transition-colors text-w-dim hover:text-white hover:bg-w-surface2/60`}
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
          className="flex-1 min-w-0 rounded border border-w-line bg-w-surface2 px-1.5 py-0.5 text-[13px] text-w-text outline-none focus:border-w-accent"
        />
      </div>
    )
  }

  // ─── Expanded sidebar ───
  return (
    <>
      <aside className="w-56 bg-w-surface border-r border-w-line flex flex-col shrink-0 overflow-hidden">
        {/* Brand */}
        <div className="flex items-center gap-2 px-3 py-3">
          <div className="w-6 h-6 rounded-md bg-w-accent/15 text-w-accent flex items-center justify-center text-[10px] font-bold shrink-0">
            {brand.replace('-', ' ').split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase()}
          </div>
          <span className="flex-1 min-w-0 truncate text-[13px] font-semibold text-w-text">{brand.replace('-', ' ')}</span>
          <button
            onClick={onToggle}
            className="shrink-0 p-1 rounded hover:bg-w-surface2 text-w-dim hover:text-white transition-colors"
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
                ? 'bg-w-surface2 text-white font-medium'
                : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
            }`}
          >
            <Home size={14} strokeWidth={1.6} />
            Home
          </button>

          {/* Filter sidebar */}
          <div className="relative mt-1 mb-1.5">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-w-faint pointer-events-none" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter sidebar…"
              className="w-full pl-7 pr-2 py-1.5 rounded-md bg-w-surface2/60 border border-w-line text-[12px] text-w-text placeholder:text-w-faint outline-none focus:border-w-accent/50 transition-colors"
            />
          </div>

          {/* Tabs — recently/currently opened items, browser-tab style */}
          {openTabs.length > 0 && (
            <div className="mb-1">
              <div className="flex items-center justify-between px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-w-faint">
                Tabs
                <button onClick={() => navigate(base)} className="hover:text-w-accent" title="New tab">
                  <Plus size={11} />
                </button>
              </div>
              <div className="space-y-0.5">
                {openTabs.map((t) => {
                  const Icon = tabIcon[t.type]
                  const active = isActive(openTabPath(t))
                  return (
                    <div
                      key={`${t.type}-${t.id}`}
                      onClick={() => navigate(openTabPath(t))}
                      className={`group w-full flex items-center gap-2 px-2.5 py-1 rounded-md text-[12px] cursor-pointer transition-colors ${
                        active ? 'bg-w-surface2 text-white font-medium' : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
                      }`}
                    >
                      <Icon size={12} className="shrink-0" />
                      <span className="flex-1 min-w-0 truncate">{t.label}</span>
                      <button
                        onClick={(e) => closeTab(e, t)}
                        className="shrink-0 opacity-0 group-hover:opacity-100 p-0.5 text-w-faint hover:text-w-text transition-all"
                        title="Close tab"
                      >
                        <X size={10} />
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Email */}
          <button
            onClick={() => navigate(`${base}/email`)}
            className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
              location.pathname === `${base}/email`
                ? 'bg-w-surface2 text-white font-medium'
                : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
            }`}
          >
            <MailOpen size={14} strokeWidth={1.6} />
            Email
          </button>

          {/* Channels */}
          <div className="mt-2">
            <button
              onClick={() => setChannelsOpen(!channelsOpen)}
              className="flex items-center justify-between w-full px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-w-dim transition-colors"
            >
              <span className="flex items-center gap-1.5">
                <Hash size={12} />
                Channels
                {/* Sections default collapsed, so without this the expanded
                    sidebar shows no unread signal at all until you open it. */}
                {!channelsOpen && !filter && totalChannelUnread > 0 && (
                  <span className="w-4 h-4 rounded-full bg-w-accent text-[9px] font-bold text-black flex items-center justify-center">
                    {totalChannelUnread > 9 ? '9+' : totalChannelUnread}
                  </span>
                )}
              </span>
              <div className="flex items-center gap-1">
                <span
                  onClick={(e) => { e.stopPropagation(); navigate(`${base}/channels`) }}
                  className="hover:text-w-accent cursor-pointer"
                  title="Browse channels"
                >
                  <Compass size={12} />
                </span>
                {canCreateChannel && (
                  <span
                    onClick={(e) => { e.stopPropagation(); setShowCreateChannel(true) }}
                    className="hover:text-w-accent cursor-pointer"
                  >
                    <Plus size={12} />
                  </span>
                )}
                <ChevronDown size={12} className={`transition-transform ${channelsOpen || filter ? '' : '-rotate-90'}`} />
              </div>
            </button>
            {(channelsOpen || !!filter) && (
              <div className="space-y-0.5 mt-0.5">
                {channels.filter((ch) => ch.name.toLowerCase().includes(filter.toLowerCase())).length === 0 && (
                  <p className="px-2.5 py-1 text-[11px] text-w-faint">No channels</p>
                )}
                {channels.filter((ch) => ch.name.toLowerCase().includes(filter.toLowerCase())).map((ch) => (
                  <div
                    key={ch.id}
                    className={`group w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors cursor-pointer ${
                      isActive(`${base}/channels/${ch.id}`)
                        ? 'bg-w-surface2 text-white font-medium'
                        : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
                    }`}
                    onClick={() => navigate(`${base}/channels/${ch.id}`)}
                  >
                    <Hash size={14} className="text-w-dim shrink-0" strokeWidth={1.6} />
                    {ch.is_paid && (
                      <span className="text-[9px] font-bold text-w-accent shrink-0">$</span>
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
                          className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 text-w-dim hover:text-w-text transition-all"
                          title="Rename"
                        >
                          <Pencil size={11} />
                        </button>
                      </>
                    )}
                    {ch.unread_count > 0 && !renaming && (
                      <span className="ml-auto w-4 h-4 rounded-full bg-w-accent text-[9px] font-bold text-white flex items-center justify-center shrink-0">
                        {ch.unread_count > 9 ? '9+' : ch.unread_count}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Projects */}
          {mwBetaLite && <div className="mt-1">
            <button
              onClick={() => setProjectsOpen(!projectsOpen)}
              className="flex items-center justify-between w-full px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-w-dim transition-colors"
            >
              <span className="flex items-center gap-1.5">
                <FolderOpen size={12} />
                Workspaces
              </span>
              <div className="flex items-center gap-1">
                <span
                  onClick={(e) => { e.stopPropagation(); setShowProjectTypePicker(true) }}
                  className="hover:text-w-accent cursor-pointer"
                >
                  <Plus size={12} />
                </span>
                <ChevronDown size={12} className={`transition-transform ${projectsOpen || filter ? '' : '-rotate-90'}`} />
              </div>
            </button>
            {(projectsOpen || !!filter) && (
              <div className="space-y-0.5 mt-0.5">
                {(() => {
                  const filteredProjects = projects.filter((p) => p.title.toLowerCase().includes(filter.toLowerCase()))
                  const renderProjectRow = (p: MWProject) => (
                    <div
                      key={p.id}
                      className={`group w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                        isActive(`${base}/projects/${p.id}`)
                          ? 'bg-w-surface2 text-white font-medium'
                          : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
                      }`}
                    >
                      <FolderOpen size={14} className="text-w-accent shrink-0" strokeWidth={1.6} />
                      {renaming?.type === 'project' && renaming.id === p.id ? (
                        renderRenameInput()
                      ) : (
                        <>
                          <button
                            onClick={() => navigate(`${base}/projects/${p.id}`)}
                            className="flex-1 min-w-0 text-left truncate"
                          >
                            {p.title}
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); startRename('project', p.id, p.title) }}
                            className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 text-w-dim hover:text-w-text transition-all"
                            title="Rename"
                          >
                            <Pencil size={11} />
                          </button>
                        </>
                      )}
                    </div>
                  )

                  if (filteredProjects.length === 0) {
                    return <p className="px-2.5 py-1 text-[11px] text-w-faint">No workspaces</p>
                  }

                  if (!isPersonal) {
                    return filteredProjects.slice(0, 10).map(renderProjectRow)
                  }

                  // Personal: group by hiring client (Unassigned last)
                  const groups = new Map<string, { name: string; items: MWProject[] }>()
                  for (const p of filteredProjects) {
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
                        <p className="px-2.5 pt-1 pb-0.5 text-[10px] uppercase tracking-wider text-w-faint truncate">
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

          } {/* end mwBetaLite Projects */}

          {/* Threads */}
          <div className="mt-1">
            <button
              onClick={() => setThreadsOpen(!threadsOpen)}
              className="flex items-center justify-between w-full px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-w-dim transition-colors"
            >
              <span className="flex items-center gap-1.5">
                <MessageSquare size={12} />
                Threads
              </span>
              <ChevronDown size={12} className={`transition-transform ${threadsOpen || filter ? '' : '-rotate-90'}`} />
            </button>
            {(threadsOpen || !!filter) && (() => {
              const filteredThreads = threads.filter((t) => t.title.toLowerCase().includes(filter.toLowerCase()))
              const myThreads = filteredThreads.filter((t) => t.collaborator_count === 0)
              const sharedThreads = filteredThreads.filter((t) => t.collaborator_count > 0)

              const renderThread = (t: MWThread) => (
                <div
                  key={t.id}
                  className={`group w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                    isActive(`${base}/${t.id}`)
                      ? 'bg-w-surface2 text-white font-medium'
                      : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
                  }`}
                >
                  <MessageSquare size={14} className="text-w-dim shrink-0" strokeWidth={1.6} />
                  {renaming?.type === 'thread' && renaming.id === t.id ? (
                    renderRenameInput()
                  ) : (
                    <>
                      <button
                        onClick={() => navigate(`${base}/${t.id}`)}
                        className="flex-1 min-w-0 text-left truncate"
                      >
                        {t.title}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); startRename('thread', t.id, t.title) }}
                        className="opacity-0 group-hover:opacity-100 shrink-0 p-0.5 text-w-dim hover:text-w-text transition-all"
                        title="Rename"
                      >
                        <Pencil size={11} />
                      </button>
                    </>
                  )}
                </div>
              )

              if (filteredThreads.length === 0) {
                return <p className="px-2.5 py-1 text-[11px] text-w-faint">No threads</p>
              }

              return (
                <div className="space-y-0.5 mt-0.5">
                  {myThreads.slice(0, 10).map(renderThread)}
                  {sharedThreads.length > 0 && (
                    <>
                      <p className="px-2.5 pt-2 pb-0.5 text-[10px] uppercase tracking-wider text-w-faint flex items-center gap-1">
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
        <div className="px-2 py-2 border-t border-w-line space-y-1">
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
          {/* Footer nav row — Inbox / People / Billing as compact icon+label buttons */}
          <div className="flex items-stretch gap-1">
            <button
              onClick={() => navigate(inboxPath)}
              className="relative flex-1 flex flex-col items-center gap-0.5 py-1.5 rounded-md text-[10px] font-medium text-w-dim hover:text-w-text hover:bg-w-surface2/50 transition-colors"
            >
              <Mail size={14} strokeWidth={1.6} />
              Inbox
              {inboxUnread > 0 && (
                <span className="absolute top-0.5 right-2.5 w-3.5 h-3.5 rounded-full bg-blue-500 text-[8px] font-bold text-white flex items-center justify-center">
                  {inboxUnread > 9 ? '!' : inboxUnread}
                </span>
              )}
            </button>
            <button
              onClick={() => navigate(`${base}/connections`)}
              className={`relative flex-1 flex flex-col items-center gap-0.5 py-1.5 rounded-md text-[10px] font-medium transition-colors ${
                isActive(`${base}/connections`)
                  ? 'bg-w-surface2 text-white'
                  : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
              }`}
            >
              <Users size={14} strokeWidth={1.6} />
              People
              {pendingConnections > 0 && (
                <span className="absolute top-0.5 right-2.5 w-3.5 h-3.5 rounded-full bg-w-accent text-[8px] font-bold text-white flex items-center justify-center">
                  {pendingConnections > 9 ? '!' : pendingConnections}
                </span>
              )}
            </button>
            <button
              onClick={() => navigate(`${base}/billing`)}
              className="flex-1 flex flex-col items-center gap-0.5 py-1.5 rounded-md text-[10px] font-medium text-w-dim hover:text-w-text hover:bg-w-surface2/50 transition-colors"
            >
              <CreditCard size={14} strokeWidth={1.6} />
              Billing
            </button>
          </div>

          {/* User profile */}
          <div className="flex items-center gap-2 px-2.5 py-2 mt-1">
            {userAvatar ? (
              <img src={userAvatar} alt={userName} className="w-7 h-7 rounded-full object-cover shrink-0" />
            ) : (
              <div className="w-7 h-7 rounded-full bg-w-surface2 flex items-center justify-center text-[11px] font-medium text-w-dim shrink-0">
                {userName.charAt(0).toUpperCase()}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-[12px] text-w-text truncate">{userName}</p>
              <p className="text-[10px] text-w-faint truncate">{userEmail}</p>
            </div>
            <button
              onClick={handleLogout}
              className="shrink-0 p-1 rounded text-w-faint hover:text-red-400 hover:bg-w-surface2/60 transition-colors"
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
            navigate(`${base}/channels/${ch.id}`)
          }}
        />
      )}

      {showProjectTypePicker && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowProjectTypePicker(false)}>
          <div className="bg-w-surface border border-w-line rounded-xl p-6 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white font-semibold">New Project</h2>
              <button onClick={() => setShowProjectTypePicker(false)} className="text-w-dim hover:text-white">
                <X size={16} />
              </button>
            </div>
            <p className="text-w-dim text-sm mb-4">What kind of project?</p>
            <div className="space-y-2">
              {([
                { type: 'general' as const, icon: FileText, label: 'Research / Report', desc: 'Build documents and plans from chat' },
                { type: 'presentation' as const, icon: Presentation, label: 'Presentation', desc: 'Create slide decks and pitch materials' },
                { type: 'recruiting' as const, icon: Users, label: 'Job Posting', desc: 'Recruiting pipeline with resumes and interviews' },
              ]).map((opt) => (
                <button
                  key={opt.type}
                  onClick={() => handleCreateProject(opt.type)}
                  className="w-full flex items-center gap-3 p-3 rounded-lg border border-w-line hover:border-w-accent hover:bg-w-surface2/60 transition-colors text-left"
                >
                  <opt.icon size={20} className="text-w-accent shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-white">{opt.label}</p>
                    <p className="text-xs text-w-dim">{opt.desc}</p>
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

      <TemplatePickerModal
        open={showTemplatePicker}
        onClose={() => setShowTemplatePicker(false)}
        onPick={handlePickTemplate}
      />
    </>
  )
}
