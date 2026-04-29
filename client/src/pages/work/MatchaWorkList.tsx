import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Pin, Archive, Loader2, FileText, Presentation, Users, X, Hash, Compass, ShieldAlert } from 'lucide-react'
import type { MWThread } from '../../types/matcha-work'
import { listChannels } from '../../api/channels'
import type { ChannelSummary } from '../../api/channels'
import { listThreads, createThread, pinThread, archiveThread, createProjectNew, fetchTaskBoard, createTask, updateTask, deleteTask, dismissAutoTask } from '../../api/matchaWork'
import type { TaskBoardResponse } from '../../api/matchaWork'
import TaskBoard from '../../components/work/TaskBoard'
import { useMe } from '../../hooks/useMe'
import OnboardingWizard, { ONBOARDING_STORAGE_KEY } from '../../components/work/OnboardingWizard'

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

type Tab = 'all' | 'active' | 'pinned' | 'archived' | 'tasks'

export default function MatchaWorkList() {
  const navigate = useNavigate()
  const { me } = useMe() // auth guard
  const [threads, setThreads] = useState<MWThread[]>([])
  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [taskBoard, setTaskBoard] = useState<TaskBoardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [showTypePicker, setShowTypePicker] = useState(false)
  const [tab, setTab] = useState<Tab>('all')
  const [error, setError] = useState('')
  const [showOnboarding, setShowOnboarding] = useState(false)

  useEffect(() => {
    if (me?.user?.role !== 'individual') return
    // Backend flag is the source of truth — survives storage wipes across browsers/devices.
    if (me.user.work_onboarded) return
    let seen = false
    try {
      seen = !!localStorage.getItem(ONBOARDING_STORAGE_KEY)
    } catch {
      /* localStorage may be blocked */
    }
    if (!seen) {
      try {
        seen = !!sessionStorage.getItem(ONBOARDING_STORAGE_KEY)
      } catch {
        /* sessionStorage may be blocked too */
      }
    }
    if (!seen) setShowOnboarding(true)
  }, [me])

  async function load() {
    setLoading(true)
    setError('')
    try {
      if (tab === 'tasks') {
        const data = await fetchTaskBoard()
        setTaskBoard(data)
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

  useEffect(() => {
    listChannels().then(setChannels).catch(() => {})
  }, [])

  const filtered = tab === 'pinned' ? threads.filter((t) => t.is_pinned) : threads

  async function handleCreate() {
    setCreating(true)
    try {
      const res = await createThread()
      navigate(`/work/${res.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create')
      setCreating(false)
    }
  }

  async function handleCreateProject(type: 'general' | 'presentation' | 'recruiting' | 'discipline') {
    setShowTypePicker(false)
    setCreating(true)
    const titles: Record<string, string> = {
      general: 'New Project',
      presentation: 'New Presentation',
      recruiting: 'New Job Posting',
      discipline: 'New Disciplinary Action',
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
    { key: 'all', label: 'All Threads' },
    { key: 'active', label: 'Active' },
    { key: 'pinned', label: 'Pinned' },
    { key: 'archived', label: 'Archived' },
    { key: 'tasks', label: 'Tasks' },
  ]

  return (
    <div className="max-w-4xl mx-auto px-3 sm:px-6 py-4 sm:py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-white">Matcha Work</h1>
        {tab !== 'tasks' && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleCreate}
              disabled={creating}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
            >
              {creating ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
              New Thread
            </button>
            <button
              onClick={() => setShowTypePicker(true)}
              disabled={creating}
              className="flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white text-sm font-medium rounded-lg border border-zinc-700 transition-colors disabled:opacity-50"
            >
              <Plus size={16} />
              New Project
            </button>
          </div>
        )}
      </div>

      {/* Your Channels */}
      {channels.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-zinc-400 uppercase tracking-wider">Your Channels</h2>
            <button onClick={() => navigate('/work/channels')} className="text-xs text-zinc-500 hover:text-emerald-400 flex items-center gap-1">
              <Compass size={12} />
              Browse All
            </button>
          </div>
          <div className="flex gap-3 overflow-x-auto pb-2 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
            {channels.filter(ch => ch.is_member).slice(0, 8).map((ch) => (
              <button
                key={ch.id}
                onClick={() => navigate(`/work/channels/${ch.id}`)}
                className="flex-shrink-0 w-48 bg-zinc-900 border border-zinc-800 rounded-lg p-3 hover:border-zinc-700 transition-colors text-left"
              >
                <div className="flex items-center gap-2 mb-1">
                  <Hash size={14} className="text-emerald-500 shrink-0" />
                  <span className="text-sm font-medium text-white truncate">{ch.name}</span>
                  {ch.is_paid && <span className="text-[9px] font-bold text-emerald-400">$</span>}
                </div>
                <div className="flex items-center gap-3 text-xs text-zinc-500">
                  <span>{ch.member_count} members</span>
                  {ch.unread_count > 0 && (
                    <span className="px-1.5 py-0.5 rounded-full bg-emerald-600 text-[10px] font-bold text-white">
                      {ch.unread_count > 9 ? '9+' : ch.unread_count}
                    </span>
                  )}
                </div>
                {ch.last_message_preview && (
                  <p className="text-xs text-zinc-600 truncate mt-1">{ch.last_message_preview}</p>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-zinc-800 overflow-x-auto whitespace-nowrap [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
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
      {showOnboarding && (
        <OnboardingWizard onDismiss={() => setShowOnboarding(false)} />
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
                { type: 'discipline' as const, icon: ShieldAlert, label: 'Disciplinary Action', desc: 'Draft, sign, and close a written warning' },
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
