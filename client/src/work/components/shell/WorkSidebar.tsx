import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { PanelLeftClose, Home, Search, ClipboardList, BookOpenCheck, Package, Archive } from 'lucide-react'
import { logoutSession } from '../../../api/client'
import type { ChannelSummary } from '../../api/channels'
import { createProjectNew, createThread, archiveThread, notifyThreadsChanged, startPersonalCheckout } from '../../api/matchaWork'
import { useMe } from '../../../hooks/useMe'
import CreateChannelModal from '../channels/CreateChannelModal'
import HiringClientPickerModal from '../panels/HiringClientPickerModal'
import TemplatePickerModal from '../panels/TemplatePickerModal'
import type { RecruitingClient, MWThread } from '../../types'
import { useWorkBase, useWorkBrand, useWorkSurface } from '../../routes/WorkSurfaceContext'
import { canCreateChannel, canCreatePaidChannel } from '../../utils/channelPermissions'
import { canReviewEvents } from '../../utils/eventsPermissions'
import { formatEventsBadge } from '../../hooks/useLoggedEventsCount'
import type { Props } from './WorkSidebar/types'
import { useSidebarData } from './WorkSidebar/useSidebarData'
import { useSectionState } from './WorkSidebar/useSectionState'
import { useSidebarRename } from './WorkSidebar/useSidebarRename'
import CollapsedRail from './WorkSidebar/CollapsedRail'
import ChannelsSection from './WorkSidebar/ChannelsSection'
import ProjectsSection from './WorkSidebar/ProjectsSection'
import ChatsSection from './WorkSidebar/ChatsSection'
import SidebarFooter from './WorkSidebar/SidebarFooter'
import ProjectTypePickerModal from './WorkSidebar/ProjectTypePickerModal'

export default function WorkSidebar({ open, onToggle }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const base = useWorkBase()
  const brand = useWorkBrand()
  const surface = useWorkSurface()
  const showChannels = surface !== 'matcha-work'
  const { me, isPersonal, mwBetaLite, hasFeature } = useMe()
  const canCreate = surface !== 'matcha-work' && canCreateChannel(me?.user?.role)
  const opsAccess = me?.ops_access ?? me?.work_access
  const showEvents = surface !== 'matcha-work' && canReviewEvents(opsAccess) && hasFeature('ems')
  const showInventory = surface !== 'matcha-work' && canReviewEvents(opsAccess) && hasFeature('inventory')
  const showAssets = canReviewEvents(me?.work_access) && hasFeature('huume')

  const {
    channels, setChannels,
    projects, setProjects,
    threads, setThreads,
    inboxUnread,
    pendingConnections,
    plusActive,
    loggedEventsCount,
  } = useSidebarData(isPersonal, base, location.pathname, showEvents, showChannels)

  const [showCreateChannel, setShowCreateChannel] = useState(false)
  const [showProjectTypePicker, setShowProjectTypePicker] = useState(false)
  const [showHiringClientPicker, setShowHiringClientPicker] = useState(false)
  const [showTemplatePicker, setShowTemplatePicker] = useState(false)

  const sections = useSectionState(base)
  const [upgrading, setUpgrading] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)
  const [filter, setFilter] = useState('')

  // Inline rename state
  const rename = useSidebarRename({ setChannels, setProjects, setThreads })

  async function handleArchiveThread(t: MWThread) {
    if (!window.confirm(`Archive "${t.title}"? You can restore it from the Archived filter on the threads page.`)) return
    try {
      await archiveThread(t.id)
      setThreads((prev) => prev.filter((x) => x.id !== t.id))
      notifyThreadsChanged()
      if (location.pathname === `${base}/${t.id}`) navigate(base)
    } catch {}
  }

  async function handleNewChat() {
    try {
      const res = await createThread()
      setThreads((prev) => [
        {
          id: res.id,
          title: res.title,
          status: res.status,
          task_type: res.task_type,
          is_pinned: res.is_pinned,
          node_mode: res.node_mode,
          compliance_mode: res.compliance_mode,
          payer_mode: res.payer_mode,
          benefits_mode: res.benefits_mode,
          legal_mode: res.legal_mode,
          risk_mode: res.risk_mode,
          training_mode: res.training_mode,
          hr_pilot_mode: res.hr_pilot_mode,
          huume_mode: res.huume_mode,
          collaborator_count: 0,
          version: res.version,
          created_at: res.created_at,
          updated_at: res.created_at,
        },
        ...prev,
      ])
      navigate(`${base}/${res.id}`)
    } catch {}
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
    // logoutSession does two sequential round-trips (refresh, then revoke)
    // before it navigates, so without this the button stays live and repeat
    // clicks stack duplicate revocation requests.
    if (loggingOut) return
    setLoggingOut(true)
    void logoutSession()
  }

  const isActive = (path: string) => location.pathname === path
  const inboxPath = `${base}/inbox`
  const visibleChannels = surface === 'matcha-work'
    ? channels.filter((channel) => channel.channel_scope === 'project_discussion' || !channel.channel_scope)
    : channels
  const totalChannelUnread = visibleChannels.reduce((sum, ch) => sum + ch.unread_count, 0)
  const userName = me?.profile?.name || me?.user?.email?.split('@')[0] || 'User'
  const userEmail = me?.user?.email || ''
  const userAvatar = me?.user?.avatar_url

  // ─── Collapsed: icon rail ───
  if (!open) {
    return (
      <CollapsedRail
        onToggle={onToggle}
        base={base}
        pathname={location.pathname}
        navigate={navigate}
        isActive={isActive}
        mwBetaLite={mwBetaLite}
        totalChannelUnread={totalChannelUnread}
        pendingConnections={pendingConnections}
        inboxUnread={inboxUnread}
        inboxPath={inboxPath}
        openChannels={() => sections.open('channels')}
        openProjects={() => sections.open('projects')}
        openChats={() => sections.open('chats')}
        showEvents={showEvents}
        showInventory={showInventory}
        showWaste={showInventory && hasFeature('inventory_waste')}
        showChannels={showChannels}
        loggedEventsCount={loggedEventsCount}
      />
    )
  }

  // ─── Expanded sidebar ───
  return (
    <>
      <aside className="w-56 bg-w-surface border-r border-w-line flex flex-col shrink-0 overflow-hidden">
        {/* Brand */}
        <div className="flex items-center gap-2 px-3 py-3">
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

          {/* Events (HR admin review of @huume-logged events) */}
          {showEvents && (
            <button
              onClick={() => navigate(`${base}/events`)}
              className={`relative w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                location.pathname.startsWith(`${base}/events`)
                  ? 'bg-w-surface2 text-white font-medium'
                  : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
              }`}
            >
              <ClipboardList size={14} strokeWidth={1.6} />
              Events
              {loggedEventsCount > 0 && (
                <span className="ml-auto w-4 h-4 rounded-full bg-w-accent text-[9px] font-bold text-white flex items-center justify-center shrink-0">
                  {formatEventsBadge(loggedEventsCount)}
                </span>
              )}
            </button>
          )}

          {/* Protocol (admin-editable event protocol Huume grounds on) */}
          {showEvents && (
            <button
              onClick={() => navigate(`${base}/protocol`)}
              className={`relative w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                location.pathname.startsWith(`${base}/protocol`)
                  ? 'bg-w-surface2 text-white font-medium'
                  : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
              }`}
            >
              <BookOpenCheck size={14} strokeWidth={1.6} />
              Protocol
            </button>
          )}

          {/* Inventory (channel-driven stock tracking via @huume) */}
          {showInventory && (
            <button
              onClick={() => navigate(`${base}/inventory`)}
              className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                location.pathname.startsWith(`${base}/inventory`)
                  ? 'bg-w-surface2 text-white font-medium'
                  : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
              }`}
            >
              <Package size={14} strokeWidth={1.6} />
              Inventory
            </button>
          )}
          {showInventory && hasFeature('inventory_waste') && <button onClick={() => navigate(`${base}/inventory/waste`)} className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] ${location.pathname.startsWith(`${base}/inventory/waste`) ? 'bg-w-surface2 text-white font-medium' : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'}`}><Package size={14} strokeWidth={1.6} /> Waste & par</button>}

          {/* Assets (company-wide feed of everything Huume has created) */}
          {showAssets && (
            <button
              onClick={() => navigate(`${base}/assets`)}
              className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-[13px] transition-colors ${
                location.pathname.startsWith(`${base}/assets`)
                  ? 'bg-w-surface2 text-white font-medium'
                  : 'text-w-dim hover:text-w-text hover:bg-w-surface2/50'
              }`}
            >
              <Archive size={14} strokeWidth={1.6} />
              Assets
            </button>
          )}

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

          {/* Chats */}
          <ChatsSection
            threads={threads}
            chatsOpen={sections.chats}
            onToggle={() => sections.toggle('chats')}
            onNewChat={handleNewChat}
            filter={filter}
            base={base}
            navigate={navigate}
            isActive={isActive}
            rename={rename}
            onArchive={handleArchiveThread}
          />

          {/* Channels */}
          {showChannels && (
            <ChannelsSection
              channels={visibleChannels}
              channelsOpen={sections.channels}
              onToggle={() => sections.toggle('channels')}
              filter={filter}
              totalChannelUnread={totalChannelUnread}
              canCreate={canCreate}
              base={base}
              navigate={navigate}
              isActive={isActive}
              setShowCreateChannel={setShowCreateChannel}
              rename={rename}
            />
          )}

          {/* Projects */}
          {mwBetaLite && (
            <ProjectsSection
              projects={projects}
              projectsOpen={sections.projects}
              onToggle={() => sections.toggle('projects')}
              filter={filter}
              isPersonal={isPersonal}
              base={base}
              navigate={navigate}
              isActive={isActive}
              setShowProjectTypePicker={setShowProjectTypePicker}
              rename={rename}
            />
          )}
        </nav>

        {/* Footer: Inbox + User profile + Logout */}
        <SidebarFooter
          isPersonal={isPersonal}
          plusActive={plusActive}
          upgrading={upgrading}
          onUpgrade={handleUpgradeToPlus}
          base={base}
          navigate={navigate}
          isActive={isActive}
          inboxPath={inboxPath}
          inboxUnread={inboxUnread}
          pendingConnections={pendingConnections}
          userAvatar={userAvatar}
          userName={userName}
          userEmail={userEmail}
          onLogout={handleLogout}
        />
      </aside>

      {showCreateChannel && (
        <CreateChannelModal
          onClose={() => setShowCreateChannel(false)}
          canCreatePaid={canCreatePaidChannel(me?.user?.role, surface)}
          onCreated={(ch) => {
            setShowCreateChannel(false)
            setChannels((prev) => [{ ...ch, member_count: 1, unread_count: 0, last_message_at: null, last_message_preview: null, is_member: true } as ChannelSummary, ...prev])
            navigate(`${base}/channels/${ch.id}`)
          }}
        />
      )}

      {showProjectTypePicker && (
        <ProjectTypePickerModal
          onClose={() => setShowProjectTypePicker(false)}
          onCreate={handleCreateProject}
        />
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
