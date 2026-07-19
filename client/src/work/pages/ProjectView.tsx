import { Link } from 'react-router-dom'
import { ChevronLeft, Loader2, MessageSquare, KanbanSquare, FileText, Hash, Sparkles } from 'lucide-react'
import ProjectKanbanBoard from '../components/shell/ProjectKanbanBoard'
import ChannelViewScreen from './ChannelView/ChannelViewScreen'
import BoardFilesTab from '../components/shell/BoardFilesTab'
import ProjectTour from '../components/panels/ProjectTour'
import { useProjectView } from './ProjectView/useProjectView'
import { ProjectSidebar } from './ProjectView/ProjectSidebar'
import { InboxPane } from './ProjectView/InboxPane'
import { ChatPane } from './ProjectView/ChatPane'
import { WorkspacePanel } from './ProjectView/WorkspacePanel'
import { TOUR_STEPS } from './ProjectView/tour'

export default function ProjectView() {
  const vm = useProjectView()
  const {
    base,
    project,
    loading,
    error,
    activeTab,
    selectTab,
    sidebarMode,
    mobileMenuOpen,
    setMobileMenuOpen,
    projectId,
    showTour,
    dismissTour,
    isCollab,
    discussionChannelId,
    channelError,
  } = vm

  if (loading) {
    return (
      <div className="flex justify-center items-center h-[calc(100vh-49px)]">
        <Loader2 className="animate-spin text-w-dim" size={24} />
      </div>
    )
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-49px)] gap-4">
        <p className="text-red-400">{error || 'Project not found'}</p>
        <Link to={base} className="text-sm text-w-dim hover:text-white">Back to threads</Link>
      </div>
    )
  }

  const isRecruiting = project.project_type === 'recruiting'
  // Scope for now: a workspace only needs Chat + Kanban (recruiting swaps in its
  // Pipeline in place of Kanban — it has no board surface anywhere else in the
  // product, so tasks created there would be orphaned). Presentations keep the
  // sections panel as "Notes": those sections ARE the deliverable, and the panel
  // is their only viewer/exporter on web. Files comes later — its render branch
  // below stays intact, just unreferenced by this tab set.
  //
  // Collab is the exception: its "Chat" is the project's discussion CHANNEL
  // (the thing collaborators actually talk in — previously only reachable via
  // the Channels sidebar), and the AI mw_threads list moves to its own tab
  // instead of impersonating the project chat with "Chat 1", "Chat 2", …
  const workspaceTabs = isRecruiting
    ? [
        { key: 'chat' as const, icon: MessageSquare, label: 'Chat' },
        { key: 'panel' as const, icon: FileText, label: 'Pipeline' },
      ]
    : isCollab
    ? [
        { key: 'chat' as const, icon: Hash, label: 'Chat' },
        { key: 'ai' as const, icon: Sparkles, label: 'AI' },
        { key: 'board' as const, icon: KanbanSquare, label: 'Kanban' },
      ]
    : project.project_type === 'presentation'
    ? [
        { key: 'chat' as const, icon: MessageSquare, label: 'Chat' },
        { key: 'panel' as const, icon: FileText, label: 'Notes' },
        { key: 'board' as const, icon: KanbanSquare, label: 'Kanban' },
      ]
    : [
        { key: 'chat' as const, icon: MessageSquare, label: 'Chat' },
        { key: 'board' as const, icon: KanbanSquare, label: 'Kanban' },
      ]
  // The sections panel is only reachable when a `panel` tab exists. Chat writes
  // into it ("Add to Project"), so that affordance has to follow the tab set —
  // otherwise sections accumulate in a surface the UI can't open.
  const hasPanelTab = workspaceTabs.some((t) => t.key === 'panel')

  return (
    <div className="flex flex-col md:flex-row h-full min-h-0 relative overflow-hidden bg-w-bg">
      {/* Mobile Sidebar Overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-40 md:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Mobile Chat Sidebar */}
      <div className={`fixed inset-y-0 left-0 z-50 transform transition-transform duration-200 ease-in-out md:hidden flex flex-col w-[240px] shrink-0 h-[calc(100dvh-49px)] top-[49px] ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'}`} style={{ borderRight: '1px solid var(--color-w-line)', background: 'var(--color-w-surface)' }}>
        <ProjectSidebar vm={vm} project={project} isRecruiting={isRecruiting} />
      </div>

      {/* Desktop Chat Sidebar — hidden for recruiting projects (single-chat
          flow, no list needed) and for collab outside the AI tab (the channel
          has no thread list to pick from). */}
      {!isRecruiting && (!isCollab || activeTab === 'ai') && (
        <div className="hidden md:flex flex-col w-[200px] shrink-0 border-r border-w-line bg-w-surface">
          <ProjectSidebar vm={vm} project={project} isRecruiting={isRecruiting} />
        </div>
      )}

      {/* Main column — back bar + tab strip (desktop) + the active surface + bottom bar (mobile) */}
      <div className="flex-1 min-w-0 min-h-0 flex flex-col">

      {/* Desktop back bar + tab strip */}
      <div className="hidden md:flex flex-col shrink-0 border-b border-w-line">
        <Link
          to={base}
          className="flex items-center gap-1 px-3 pt-2.5 pb-1 text-[12px] text-w-dim hover:text-w-text transition-colors w-fit"
        >
          <ChevronLeft size={13} />
          Workspaces
        </Link>
        <div className="flex items-center gap-1 px-2.5 pb-2">
          {workspaceTabs.map((t) => (
            <button
              key={t.key}
              onClick={() => selectTab(t.key)}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[13px] font-medium transition-colors border ${
                activeTab === t.key
                  ? 'bg-w-surface2 border-w-line text-w-accent'
                  : 'border-transparent text-w-dim hover:text-w-text hover:bg-w-surface2/60'
              }`}
            >
              <t.icon size={14} />
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Center — inbox view when sidebar is in inbox mode */}
      {sidebarMode === 'inbox' && (
        <InboxPane vm={vm} />
      )}

      {/* Center — the project's real chat (collab): its discussion channel.
          Reuses the full channel surface (realtime WS, calls, mentions,
          uploads, members) with the id passed in rather than read from the
          route — this path has no :channelId.

          Once resolved it stays MOUNTED and hides via CSS (like ChatPane
          below) rather than unmounting per tab: ChannelViewScreen owns the
          channel WebSocket, so conditional mounting tore the socket down and
          rebuilt it — refetching history and dropping the composer draft — on
          every Chat↔Kanban flip. */}
      {isCollab && discussionChannelId && (
        <div
          className={`flex-1 min-h-0 flex-col bg-w-bg ${
            activeTab === 'chat' && sidebarMode === 'chats' ? 'flex' : 'hidden'
          }`}
        >
          <ChannelViewScreen channelId={discussionChannelId} embedded />
        </div>
      )}

      {/* Loading / failure for that pane, only until an id resolves. */}
      {isCollab && !discussionChannelId && activeTab === 'chat' && sidebarMode === 'chats' && (
        <div className="flex-1 min-h-0 flex flex-col items-center justify-center bg-w-bg px-6 text-center">
          {channelError ? (
            <p className="text-sm text-red-400">{channelError}</p>
          ) : (
            <Loader2 className="animate-spin text-w-dim" size={20} />
          )}
        </div>
      )}

      {/* Center — AI chat messages. Its own tab for collab, the `chat` tab
          for every other project type. */}
      {sidebarMode === 'chats' && (
        <ChatPane vm={vm} project={project} isRecruiting={isRecruiting} hasPanelTab={hasPanelTab} />
      )}

      {/* Right — Project panel or Recruiting pipeline */}
      <WorkspacePanel vm={vm} project={project} />

      {/* Kanban board */}
      {activeTab === 'board' && !isRecruiting && (
        <div className="flex-1 min-h-0 flex flex-col bg-w-bg">
          <ProjectKanbanBoard projectId={projectId!} />
        </div>
      )}

      {/* Files */}
      {activeTab === 'files' && (
        <div className="flex-1 min-h-0 flex flex-col bg-w-bg">
          <BoardFilesTab projectId={projectId!} />
        </div>
      )}

      {/* Mobile bottom tab bar — same tab set as the desktop strip */}
      <nav
        className="md:hidden shrink-0 flex items-stretch border-t border-w-line bg-w-surface"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        {workspaceTabs.map((t) => {
          const active = activeTab === t.key
          return (
            <button
              key={t.key}
              onClick={() => selectTab(t.key)}
              className={`flex-1 flex flex-col items-center justify-center gap-0.5 py-2 transition-colors ${
                active ? 'text-w-accent' : 'text-w-dim'
              }`}
            >
              <span
                className={`flex items-center justify-center rounded-lg px-3.5 py-1 transition-colors ${
                  active ? 'bg-w-accent/15' : ''
                }`}
              >
                <t.icon size={18} />
              </span>
              <span className="text-[10px] font-medium">{t.label}</span>
            </button>
          )
        })}
      </nav>

      </div>

      {showTour && project.project_type !== 'recruiting' && (
        // Three of the four steps point into the sections panel (and its export
        // button). Without a panel tab those targets never render, and the tour
        // would narrate — then dead-end on — UI the user can't reach.
        <ProjectTour
          steps={hasPanelTab ? TOUR_STEPS : TOUR_STEPS.filter((s) => s.target === '[data-tour="chat-input"]')}
          onComplete={dismissTour}
        />
      )}
    </div>
  )
}
