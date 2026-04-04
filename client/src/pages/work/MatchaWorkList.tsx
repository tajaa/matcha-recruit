import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Pin, Archive, Loader2, FolderOpen, FileText, Presentation, Users, X, Hash } from 'lucide-react'
import type { MWThread, MWProject } from '../../types/matcha-work'
import { listThreads, createThread, pinThread, archiveThread, listProjects, createProjectNew, fetchTaskBoard, createTask, updateTask, deleteTask, dismissAutoTask } from '../../api/matchaWork'
import type { TaskBoardResponse } from '../../api/matchaWork'
import TaskBoard from '../../components/work/TaskBoard'
import { listChannels } from '../../api/channels'
import type { ChannelSummary } from '../../api/channels'
import CreateChannelModal from '../../components/channels/CreateChannelModal'
import { useMe } from '../../hooks/useMe'

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

type Tab = 'all' | 'active' | 'pinned' | 'archived' | 'projects' | 'tasks' | 'channels'

export default function MatchaWorkList() {
  const navigate = useNavigate()
  const { me } = useMe()
  const canCreateChannel = me?.user?.role === 'client' || me?.user?.role === 'admin'
  const [threads, setThreads] = useState<MWThread[]>([])
  const [projects, setProjects] = useState<MWProject[]>([])
  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [taskBoard, setTaskBoard] = useState<TaskBoardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [showTypePicker, setShowTypePicker] = useState(false)
  const [showCreateChannel, setShowCreateChannel] = useState(false)
  const [tab, setTab] = useState<Tab>('projects')
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      if (tab === 'channels') {
        const data = await listChannels()
        setChannels(data)
      } else if (tab === 'tasks') {
        const data = await fetchTaskBoard()
        setTaskBoard(data)
      } else if (tab === 'projects') {
        const data = await listProjects()
        setProjects(data)
      } else {
        const status = tab === 'active' ? 'active' : tab === 'archived' ? 'archived' : undefined
        const data = await listThreads(status)
        setThreads(data)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [tab])

  const filtered = tab === 'pinned' ? threads.filter((t) => t.is_pinned) : threads

  async function handleCreate() {
    if (tab === 'projects') {
      setShowTypePicker(true)
      return
    }
    setCreating(true)
    try {
      const res = await createThread()
      navigate(`/work/${res.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create')
      setCreating(false)
    }
  }

  async function handleCreateProject(type: 'general' | 'presentation' | 'recruiting') {
    setShowTypePicker(false)
    setCreating(true)
    const titles: Record<string, string> = {
      general: 'New Project',
      presentation: 'New Presentation',
      recruiting: 'New Job Posting',
    }
    try {
      const res = await createProjectNew(titles[type], type)
      navigate(`/work/projects/${res.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create')
      setCreating(false)
    }
  }

  async function handlePin(e: React.MouseEvent, t: MWThread) {
    e.stopPropagation()
    try {
      await pinThread(t.id, !t.is_pinned)
      setThreads((prev) =>
        prev.map((x) => (x.id === t.id ? { ...x, is_pinned: !x.is_pinned } : x))
      )
    } catch {}
  }

  async function handleArchive(e: React.MouseEvent, t: MWThread) {
    e.stopPropagation()
    try {
      await archiveThread(t.id)
      setThreads((prev) => prev.filter((x) => x.id !== t.id))
    } catch {}
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'active', label: 'Active' },
    { key: 'pinned', label: 'Pinned' },
    { key: 'archived', label: 'Archived' },
    { key: 'projects', label: 'Projects' },
    { key: 'tasks', label: 'Tasks' },
    { key: 'channels', label: 'Channels' },
  ]

  return (
    <div className="max-w-4xl mx-auto px-3 sm:px-6 py-4 sm:py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-white">Matcha Work</h1>
        {tab === 'channels' ? (
          canCreateChannel && (
            <button
              onClick={() => setShowCreateChannel(true)}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <Plus size={16} />
              New Channel
            </button>
          )
        ) : tab !== 'tasks' && (
          <button
            onClick={handleCreate}
            disabled={creating}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            {creating ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
            {tab === 'projects' ? 'New Project' : 'New Thread'}
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-zinc-800 overflow-x-auto flex-nowrap">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === t.key
                ? 'border-emerald-500 text-white'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-300 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="animate-spin text-zinc-500" size={24} />
        </div>
      ) : tab === 'tasks' ? (
        <TaskBoard
          autoItems={taskBoard?.auto_items ?? []}
          manualItems={taskBoard?.manual_items ?? []}
          dismissedIds={taskBoard?.dismissed_ids ?? []}
          onCreateTask={async (body) => {
            const newTask = await createTask(body)
            setTaskBoard((prev) => prev ? { ...prev, manual_items: [newTask, ...prev.manual_items], total: prev.total + 1 } : prev)
          }}
          onCompleteTask={async (id) => {
            await updateTask(id, { status: 'completed' })
            setTaskBoard((prev) => prev ? {
              ...prev,
              manual_items: prev.manual_items.map((t) => t.id === id ? { ...t, status: 'completed' } : t),
            } : prev)
          }}
          onUncompleteTask={async (id) => {
            await updateTask(id, { status: 'pending' })
            setTaskBoard((prev) => prev ? {
              ...prev,
              manual_items: prev.manual_items.map((t) => t.id === id ? { ...t, status: 'pending', completed_at: null } : t),
            } : prev)
          }}
          onDismiss={async (category, sourceId) => {
            await dismissAutoTask(category, sourceId)
            setTaskBoard((prev) => prev ? {
              ...prev,
              dismissed_ids: [...prev.dismissed_ids, `${category}:${sourceId}`],
            } : prev)
          }}
          onDeleteTask={async (id) => {
            await deleteTask(id)
            setTaskBoard((prev) => prev ? {
              ...prev,
              manual_items: prev.manual_items.filter((t) => t.id !== id),
              total: prev.total - 1,
            } : prev)
          }}
        />
      ) : tab === 'channels' ? (
        channels.length === 0 ? (
          <div className="text-center py-16 text-zinc-500">No channels yet.{canCreateChannel ? ' Create one to get started.' : ''}</div>
        ) : (
          <div className="space-y-2">
            {channels.map((ch) => (
              <div
                key={ch.id}
                onClick={() => navigate(`/work/channels/${ch.id}`)}
                className="group flex items-center gap-4 p-4 bg-zinc-900 hover:bg-zinc-800/80 border border-zinc-800 rounded-lg cursor-pointer transition-colors"
              >
                <Hash size={18} className="text-emerald-500 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-white font-medium truncate">{ch.name}</span>
                    <span className="shrink-0 px-2 py-0.5 text-xs font-medium rounded-full bg-zinc-700 text-zinc-300">
                      {ch.member_count} member{ch.member_count !== 1 ? 's' : ''}
                    </span>
                    {!ch.is_member && (
                      <span className="shrink-0 px-2 py-0.5 text-xs font-medium rounded-full bg-zinc-700 text-amber-300">
                        Not joined
                      </span>
                    )}
                    {ch.unread_count > 0 && (
                      <span className="shrink-0 w-5 h-5 flex items-center justify-center text-[10px] font-bold rounded-full bg-emerald-600 text-white">
                        {ch.unread_count > 9 ? '9+' : ch.unread_count}
                      </span>
                    )}
                  </div>
                  <div className="mt-1 flex items-center gap-3 text-xs text-zinc-500">
                    {ch.last_message_preview && <span className="truncate max-w-[250px]">{ch.last_message_preview}</span>}
                    {ch.last_message_at && <span>{new Date(ch.last_message_at).toLocaleDateString()}</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      ) : tab === 'projects' ? (
        projects.length === 0 ? (
          <div className="text-center py-16 text-zinc-500">No projects yet. Create one to get started.</div>
        ) : (
          <div className="space-y-2">
            {projects.map((p) => (
              <div
                key={p.id}
                onClick={() => navigate(`/work/projects/${p.id}`)}
                className="group flex items-center gap-4 p-4 bg-zinc-900 hover:bg-zinc-800/80 border border-zinc-800 rounded-lg cursor-pointer transition-colors"
              >
                <FolderOpen size={18} className="text-[#ce9178] shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    {p.is_pinned && <Pin size={12} className="text-amber-400 shrink-0" />}
                    <span className="text-white font-medium truncate">{p.title}</span>
                    <span className="shrink-0 px-2 py-0.5 text-xs font-medium rounded-full bg-zinc-700 text-zinc-300">
                      {p.chat_count} chat{p.chat_count !== 1 ? 's' : ''}
                    </span>
                    {p.collaborator_role === 'collaborator' && (
                      <span className="shrink-0 px-2 py-0.5 text-xs font-medium rounded-full bg-blue-900/40 text-blue-300 flex items-center gap-1">
                        <Users size={10} />Shared
                      </span>
                    )}
                  </div>
                  <div className="mt-1 flex items-center gap-3 text-xs text-zinc-500">
                    <span>{p.sections?.length ?? 0} sections</span>
                    <span>{new Date(p.updated_at).toLocaleDateString()}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-zinc-500">
          {tab === 'pinned' ? 'No pinned threads' : 'No threads yet. Create one to get started.'}
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((t) => (
            <div
              key={t.id}
              onClick={() => navigate(`/work/${t.id}`)}
              className="group flex items-center gap-4 p-4 bg-zinc-900 hover:bg-zinc-800/80 border border-zinc-800 rounded-lg cursor-pointer transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  {t.is_pinned && <Pin size={12} className="text-amber-400 shrink-0" />}
                  <span className="text-white font-medium truncate">{t.title}</span>
                  {t.task_type && (
                    <span className="shrink-0 px-2 py-0.5 text-xs font-medium rounded-full bg-zinc-700 text-zinc-300">
                      {TASK_LABELS[t.task_type] ?? t.task_type}
                    </span>
                  )}
                  {t.node_mode && (
                    <span className="shrink-0 px-1.5 py-0.5 text-[11px] sm:text-[10px] font-medium rounded-full bg-purple-700 text-purple-200">
                      Node
                    </span>
                  )}
                  {t.compliance_mode && (
                    <span className="shrink-0 px-1.5 py-0.5 text-[11px] sm:text-[10px] font-medium rounded-full bg-cyan-700 text-cyan-200">
                      Compliance
                    </span>
                  )}
                </div>
                <div className="mt-1 flex items-center gap-3 text-xs text-zinc-500">
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
                      className={`p-1.5 rounded hover:bg-zinc-700 ${
                        t.is_pinned ? 'text-amber-400' : 'text-zinc-500'
                      }`}
                      title={t.is_pinned ? 'Unpin' : 'Pin'}
                    >
                      <Pin size={14} />
                    </button>
                    <button
                      onClick={(e) => handleArchive(e, t)}
                      className="p-1.5 rounded hover:bg-zinc-700 text-zinc-500"
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
      {/* Create channel modal */}
      {showCreateChannel && (
        <CreateChannelModal
          onClose={() => setShowCreateChannel(false)}
          onCreated={(ch) => {
            setShowCreateChannel(false)
            navigate(`/work/channels/${ch.id}`)
          }}
        />
      )}

      {/* Project type picker modal */}
      {showTypePicker && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-sm mx-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-white font-semibold">New Project</h2>
              <button onClick={() => setShowTypePicker(false)} className="text-zinc-500 hover:text-white">
                <X size={16} />
              </button>
            </div>
            <p className="text-zinc-400 text-sm mb-4">What kind of project?</p>
            <div className="space-y-2">
              {[
                { type: 'general' as const, icon: FileText, label: 'Research / Report', desc: 'Build documents and plans from chat' },
                { type: 'presentation' as const, icon: Presentation, label: 'Presentation', desc: 'Create slide decks and pitch materials' },
                { type: 'recruiting' as const, icon: Users, label: 'Job Posting', desc: 'Recruiting pipeline with resumes and interviews' },
              ].map((opt) => (
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
    </div>
  )
}
