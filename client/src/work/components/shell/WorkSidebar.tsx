import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { PanelLeftClose, Home, Search, MailOpen } from 'lucide-react'
import { disconnectSharedChannelSocket } from '../../api/channelSocket'
import { resetAuthCaches } from '../../../api/authReset'
import type { ChannelSummary } from '../../api/channels'
import { createProjectNew, startPersonalCheckout } from '../../api/matchaWork'
import { useMe } from '../../../hooks/useMe'
import CreateChannelModal from '../channels/CreateChannelModal'
import HiringClientPickerModal from '../panels/HiringClientPickerModal'
import TemplatePickerModal from '../panels/TemplatePickerModal'
import type { RecruitingClient } from '../../types'
import { useWorkBase, useWorkBrand, useWorkSurface } from '../../routes/WorkSurfaceContext'
import { canCreateChannel, canCreatePaidChannel } from '../../utils/channelPermissions'
import type { Props } from './WorkSidebar/types'
import { useSidebarData } from './WorkSidebar/useSidebarData'
import { useOpenTabs } from './WorkSidebar/useOpenTabs'
import { useSidebarRename } from './WorkSidebar/useSidebarRename'
import CollapsedRail from './WorkSidebar/CollapsedRail'
import SidebarTabs from './WorkSidebar/SidebarTabs'
import ChannelsSection from './WorkSidebar/ChannelsSection'
import ProjectsSection from './WorkSidebar/ProjectsSection'
import ThreadsSection from './WorkSidebar/ThreadsSection'
import SidebarFooter from './WorkSidebar/SidebarFooter'
import ProjectTypePickerModal from './WorkSidebar/ProjectTypePickerModal'

export default function WorkSidebar({ open, onToggle }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const base = useWorkBase()
  const brand = useWorkBrand()
  const surface = useWorkSurface()
  const { me, isPersonal, mwBetaLite } = useMe()
  const canCreate = canCreateChannel(me?.user?.role)

  const {
    channels, setChannels,
    projects, setProjects,
    threads, setThreads,
    inboxUnread,
    pendingConnections,
    plusActive,
  } = useSidebarData(isPersonal, base, location.pathname)

  const [showCreateChannel, setShowCreateChannel] = useState(false)
  const [showProjectTypePicker, setShowProjectTypePicker] = useState(false)
  const [showHiringClientPicker, setShowHiringClientPicker] = useState(false)
  const [showTemplatePicker, setShowTemplatePicker] = useState(false)

  const [channelsOpen, setChannelsOpen] = useState(false)
  const [projectsOpen, setProjectsOpen] = useState(false)
  const [threadsOpen, setThreadsOpen] = useState(false)
  const [upgrading, setUpgrading] = useState(false)
  const [filter, setFilter] = useState('')

  const { openTabs, closeTab, openTabPath } = useOpenTabs(base, location.pathname, channels, projects, threads)

  // Inline rename state
  const rename = useSidebarRename({ setChannels, setProjects, setThreads })

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
        setChannelsOpen={setChannelsOpen}
        setProjectsOpen={setProjectsOpen}
        setThreadsOpen={setThreadsOpen}
      />
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
          <SidebarTabs
            openTabs={openTabs}
            base={base}
            navigate={navigate}
            isActive={isActive}
            openTabPath={openTabPath}
            closeTab={closeTab}
          />

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
          <ChannelsSection
            channels={channels}
            channelsOpen={channelsOpen}
            setChannelsOpen={setChannelsOpen}
            filter={filter}
            totalChannelUnread={totalChannelUnread}
            canCreate={canCreate}
            base={base}
            navigate={navigate}
            isActive={isActive}
            setShowCreateChannel={setShowCreateChannel}
            rename={rename}
          />

          {/* Projects */}
          {mwBetaLite && (
            <ProjectsSection
              projects={projects}
              projectsOpen={projectsOpen}
              setProjectsOpen={setProjectsOpen}
              filter={filter}
              isPersonal={isPersonal}
              base={base}
              navigate={navigate}
              isActive={isActive}
              setShowProjectTypePicker={setShowProjectTypePicker}
              rename={rename}
            />
          )}

          {/* Threads */}
          <ThreadsSection
            threads={threads}
            threadsOpen={threadsOpen}
            setThreadsOpen={setThreadsOpen}
            filter={filter}
            base={base}
            navigate={navigate}
            isActive={isActive}
            rename={rename}
          />
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
