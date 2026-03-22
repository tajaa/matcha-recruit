import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Pin, Archive, Loader2 } from 'lucide-react'
import type { MWThread } from '../../types/matcha-work'
import { listThreads, createThread, pinThread, archiveThread } from '../../api/matchaWork'

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

type Tab = 'all' | 'active' | 'pinned' | 'archived'

export default function MatchaWorkList() {
  const navigate = useNavigate()
  const [threads, setThreads] = useState<MWThread[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [tab, setTab] = useState<Tab>('all')
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      const status = tab === 'active' ? 'active' : tab === 'archived' ? 'archived' : undefined
      const data = await listThreads(status)
      setThreads(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load threads')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [tab])

  const filtered = tab === 'pinned' ? threads.filter((t) => t.is_pinned) : threads

  async function handleCreate() {
    setCreating(true)
    try {
      const res = await createThread()
      navigate(`/work/${res.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create thread')
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
  ]

  return (
    <div className="max-w-4xl mx-auto px-3 sm:px-6 py-4 sm:py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-white">Matcha Work</h1>
        <button
          onClick={handleCreate}
          disabled={creating}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
        >
          {creating ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
          New Thread
        </button>
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
    </div>
  )
}
