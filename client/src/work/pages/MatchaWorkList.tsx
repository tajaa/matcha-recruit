import { Plus, Pin, Archive, Loader2, FileText, Presentation, Users, X, Hash, Compass, ShieldAlert, KanbanSquare, Search } from 'lucide-react'
import TaskBoard from '../components/shell/TaskBoard'
import { THREAD_MODE_TOGGLES } from '../components/panels/constants'
import OnboardingWizard from '../components/shell/OnboardingWizard'
import { useMatchaWorkList } from './useMatchaWorkList'

const TASK_LABELS: Record<string, string> = {
  chat: 'Chat',
  offer_letter: 'Offer Letter',
  review: 'Review',
  workbook: 'Workbook',
  onboarding: 'Onboarding',
  presentation: 'Presentation',
  handbook: 'Handbook',
  policy: 'Policy',
}

/** Dashboard card shell — hairline-bordered surface, matching desktop Werk's elevatedCard. */
function Card({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-xl bg-w-surface border border-w-line overflow-hidden">
      <div className="flex items-center justify-between gap-3 px-4 pt-3.5 pb-2.5">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-w-dim">{title}</h2>
        {action}
      </div>
      <div className="px-4 pb-4">{children}</div>
    </section>
  )
}

export default function MatchaWorkList() {
  const {
    base,
    navigate,
    channels,
    taskBoard,
    loading,
    creating,
    showTypePicker,
    setShowTypePicker,
    tab,
    setTab,
    query,
    setQuery,
    error,
    showOnboarding,
    setShowOnboarding,
    tabs,
    firstName,
    searching,
    matchedProjects,
    matchedChannels,
    matchedThreads,
    openTaskCount,
    handleCreate,
    handleCreateProject,
    handlePin,
    handleArchive,
    handleTaskCreate,
    handleTaskComplete,
    handleTaskUncomplete,
    handleTaskDismiss,
    handleTaskDelete,
  } = useMatchaWorkList()

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-8 py-8 sm:py-12">
      {/* Greeting hero + cross-surface search — mirrors desktop Werk's HomeDashboardView */}
      <header className="mb-7">
        <h1 className="text-2xl sm:text-[32px] leading-tight font-semibold tracking-tight text-w-text">
          What are we working on today{firstName ? `, ${firstName}` : ''}?
        </h1>
        <div className="mt-5 flex flex-col sm:flex-row gap-2.5">
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-w-faint pointer-events-none" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search workspaces, channels, threads…"
              className="w-full h-11 pl-10 pr-3 rounded-xl bg-w-surface border border-w-line text-sm text-w-text placeholder:text-w-faint focus:outline-none focus:border-w-accent/60 transition-colors"
            />
          </div>
          <div className="flex items-center gap-2.5">
            <button
              onClick={handleCreate}
              disabled={creating}
              className="flex-1 sm:flex-none flex items-center justify-center gap-2 h-11 px-4 bg-w-accent hover:bg-w-accent-hi text-black text-sm font-medium rounded-xl transition-colors disabled:opacity-50"
            >
              {creating ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
              New Chat
            </button>
            <button
              onClick={() => setShowTypePicker(true)}
              disabled={creating}
              className="flex-1 sm:flex-none flex items-center justify-center gap-2 h-11 px-4 bg-w-surface hover:bg-w-surface2 text-w-text text-sm font-medium rounded-xl border border-w-line transition-colors disabled:opacity-50"
            >
              <Plus size={16} />
              Workspace
            </button>
          </div>
        </div>
      </header>

      <div className="space-y-3">

      {/* Your tasks — the dashboard focal point, like desktop's "Assigned to me".
          Always rendered (not gated on a count): TaskBoard hosts the only
          create-task input and the completed list, so hiding it at zero would
          leave no way to add a first task or reopen a finished one. */}
      {!searching && (
        <Card title={openTaskCount > 0 ? `Your tasks · ${openTaskCount}` : 'Your tasks'}>
          <TaskBoard
            autoItems={taskBoard?.auto_items ?? []}
            manualItems={taskBoard?.manual_items ?? []}
            dismissedIds={taskBoard?.dismissed_ids ?? []}
            onCreateTask={handleTaskCreate}
            onCompleteTask={handleTaskComplete}
            onUncompleteTask={handleTaskUncomplete}
            onDismiss={handleTaskDismiss}
            onDeleteTask={handleTaskDelete}
          />
        </Card>
      )}

      {/* Workspaces — kanban board, notes and files live inside each */}
      {matchedProjects.length > 0 && (
        <Card title="Workspaces">
          <div className="flex gap-2.5 overflow-x-auto pb-1 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
            {matchedProjects.slice(0, 10).map((p) => {
              const Icon = p.project_type === 'presentation' ? Presentation : p.project_type === 'recruiting' ? Users : FileText
              const typeLabel = p.project_type === 'presentation' ? 'Presentation' : p.project_type === 'recruiting' ? 'Recruiting' : 'Workspace'
              return (
                <button
                  key={p.id}
                  onClick={() => navigate(`${base}/projects/${p.id}`)}
                  className="flex-shrink-0 w-52 rounded-xl bg-w-surface2/60 border border-w-line p-3.5 hover:border-w-accent/50 hover:bg-w-surface2 transition-colors text-left"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Icon size={14} className="text-w-accent shrink-0" />
                    <span className="text-[13px] font-medium text-w-text truncate">{p.title}</span>
                    {p.is_pinned && <Pin size={11} className="text-w-faint shrink-0" />}
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] text-w-faint">
                    <span>{typeLabel}</span>
                    <span>·</span>
                    <KanbanSquare size={11} />
                    <span>Board · Notes · Files</span>
                  </div>
                </button>
              )
            })}
          </div>
        </Card>
      )}

      {/* Channels — shown whenever any channel exists, even with no memberships:
          the card's "Browse all" is the dashboard's only discovery entry point. */}
      {(searching ? matchedChannels.length > 0 : channels.length > 0) && (
        <Card
          title="Channels"
          action={
            <button onClick={() => navigate(`${base}/channels`)} className="text-[11px] text-w-dim hover:text-w-accent flex items-center gap-1 transition-colors">
              <Compass size={12} />
              Browse all
            </button>
          }
        >
          {matchedChannels.length === 0 && (
            <p className="text-[12px] text-w-faint">
              You haven't joined any channels yet — browse all to find one.
            </p>
          )}
          <div className="flex gap-2.5 overflow-x-auto pb-1 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
            {matchedChannels.slice(0, 10).map((ch) => (
              <button
                key={ch.id}
                onClick={() => navigate(`${base}/channels/${ch.id}`)}
                className="flex-shrink-0 w-52 rounded-xl bg-w-surface2/60 border border-w-line p-3.5 hover:border-w-accent/50 hover:bg-w-surface2 transition-colors text-left"
              >
                <div className="flex items-center gap-2 mb-2">
                  <Hash size={14} className="text-w-accent shrink-0" />
                  <span className="text-[13px] font-medium text-w-text truncate">{ch.name}</span>
                  {ch.is_paid && <span className="text-[10px] font-bold text-w-accent">$</span>}
                  {ch.unread_count > 0 && (
                    <span className="ml-auto shrink-0 px-1.5 py-0.5 rounded-full bg-w-accent text-[10px] font-bold text-black">
                      {ch.unread_count > 9 ? '9+' : ch.unread_count}
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-w-faint truncate">
                  {ch.last_message_preview || `${ch.member_count} members`}
                </p>
              </button>
            ))}
          </div>
        </Card>
      )}

      {/* Threads — the tab filter now lives inside the card, not over the page */}
      <Card
        title="Threads"
        action={
          <div className="flex gap-1 overflow-x-auto whitespace-nowrap [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors ${
              tab === t.key
                ? 'bg-w-accent/15 text-w-accent'
                : 'text-w-dim hover:text-w-text hover:bg-w-surface2'
            }`}
          >
            {t.label}
          </button>
        ))}
          </div>
        }
      >
      {error && (
        <div className="mb-3 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="animate-spin text-w-faint" size={22} />
        </div>
      ) : matchedThreads.length === 0 ? (
        <div className="text-center py-12 text-sm text-w-faint">
          {searching ? 'No matches' : tab === 'pinned' ? 'No pinned threads' : 'No threads yet. Start a new chat.'}
        </div>
      ) : (
        <div className="space-y-1">
          {matchedThreads.map((t) => (
            <div
              key={t.id}
              onClick={() => navigate(`${base}/${t.id}`)}
              className="group flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-w-surface2 cursor-pointer transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  {t.is_pinned && <Pin size={11} className="text-w-accent shrink-0" />}
                  <span className="text-[13px] text-w-text font-medium truncate">{t.title}</span>
                  {t.task_type && (
                    <span className="shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded-full bg-w-surface2 text-w-dim">
                      {TASK_LABELS[t.task_type] ?? t.task_type}
                    </span>
                  )}
                  {THREAD_MODE_TOGGLES.filter((m) => t[`${m.key}_mode`]).map((m) => (
                    <span
                      key={m.key}
                      className={`shrink-0 px-1.5 py-0.5 text-[11px] sm:text-[10px] font-medium rounded-full ${m.badgeClass}`}
                    >
                      {m.label}
                    </span>
                  ))}
                </div>
                <div className="mt-0.5 flex items-center gap-2.5 text-[11px] text-w-faint">
                  <span>v{t.version}</span>
                  <span>{new Date(t.updated_at).toLocaleDateString()}</span>
                  <span className="capitalize">{t.status}</span>
                </div>
              </div>

              <div className="flex items-center gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
                {t.status !== 'archived' && (
                  <>
                    <button
                      onClick={(e) => handlePin(e, t)}
                      className={`p-1.5 rounded-md hover:bg-w-surface ${
                        t.is_pinned ? 'text-w-accent' : 'text-w-faint'
                      }`}
                      title={t.is_pinned ? 'Unpin' : 'Pin'}
                    >
                      <Pin size={14} />
                    </button>
                    <button
                      onClick={(e) => handleArchive(e, t)}
                      className="p-1.5 rounded-md hover:bg-w-surface text-w-faint"
                      title="Archive"
                    >
                      <Archive size={14} />
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      </Card>
      </div>

      {showOnboarding && (
        <OnboardingWizard onDismiss={() => setShowOnboarding(false)} />
      )}

      {/* Project type picker modal */}
      {showTypePicker && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-w-surface border border-w-line rounded-2xl p-6 w-full max-w-sm mx-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-w-text font-semibold">New workspace</h2>
              <button onClick={() => setShowTypePicker(false)} className="text-w-faint hover:text-w-text">
                <X size={16} />
              </button>
            </div>
            <p className="text-w-dim text-sm mb-4">What kind of workspace?</p>
            <div className="space-y-2">
              {[
                { type: 'general' as const, icon: FileText, label: 'Research / Report', desc: 'Build documents and plans from chat' },
                { type: 'presentation' as const, icon: Presentation, label: 'Presentation', desc: 'Create slide decks and pitch materials' },
                { type: 'recruiting' as const, icon: Users, label: 'Job Posting', desc: 'Recruiting pipeline with resumes and interviews' },
                { type: 'discipline' as const, icon: ShieldAlert, label: 'Performance Action', desc: 'Draft, sign, and close a written warning' },
              ].map((opt) => (
                <button
                  key={opt.type}
                  onClick={() => handleCreateProject(opt.type)}
                  className="w-full flex items-center gap-3 p-3 rounded-xl border border-w-line hover:border-w-accent/60 hover:bg-w-surface2 transition-colors text-left"
                >
                  <opt.icon size={20} className="text-w-accent shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-w-text">{opt.label}</p>
                    <p className="text-xs text-w-dim">{opt.desc}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
