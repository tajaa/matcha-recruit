import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Loader2, MessageSquare, Kanban as KanbanIcon, Files } from 'lucide-react'
import { getProjectDetail } from '../api/matchaWork'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import ProjectKanbanBoard from '../components/shell/ProjectKanbanBoard'
import BoardChatTab from '../components/shell/BoardChatTab'
import BoardFilesTab from '../components/shell/BoardFilesTab'

type BoardTab = 'chat' | 'kanban' | 'files'

const TABS: { key: BoardTab; label: string; icon: typeof KanbanIcon }[] = [
  { key: 'chat', label: 'Chat', icon: MessageSquare },
  { key: 'kanban', label: 'Kanban', icon: KanbanIcon },
  { key: 'files', label: 'Files', icon: Files },
]

// A werk-lite "Board" is a matcha-work project under the hood — the kanban is
// the primary surface, but every project also gets an AI chat thread and file
// storage for free, so this page tabs between the three (mirrors the desktop
// Werk collab project's tab strip, minus the tabs with no web surface yet).
export default function BoardView() {
  const { projectId } = useParams<{ projectId: string }>()
  const base = useWorkBase()

  const [title, setTitle] = useState<string | null>(null)
  const [titleLoading, setTitleLoading] = useState(true)
  const [tab, setTab] = useState<BoardTab>('kanban')

  useEffect(() => {
    if (!projectId) return
    let active = true
    setTitleLoading(true)
    getProjectDetail(projectId)
      .then((p) => {
        if (active) setTitle(p.title)
      })
      .catch(() => {
        // A missing/forbidden project still renders the board, which surfaces
        // its own load error — don't block the header on the title fetch.
      })
      .finally(() => {
        if (active) setTitleLoading(false)
      })
    return () => {
      active = false
    }
  }, [projectId])

  if (!projectId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-w-bg text-center">
        <p className="text-sm text-w-dim">No board selected.</p>
        <Link
          to={`${base}`}
          className="text-sm font-medium text-w-accent hover:text-w-accent-hi"
        >
          Back to boards
        </Link>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-w-bg">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-w-line px-4 py-3">
        <Link
          to={`${base}`}
          className="shrink-0 text-w-dim transition-colors hover:text-w-text"
          title="Back to boards"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <h1 className="flex items-center gap-2 truncate text-lg font-semibold text-w-text">
          {title ?? (titleLoading ? <Loader2 className="h-4 w-4 animate-spin text-w-dim" /> : 'Board')}
        </h1>
      </div>

      {/* Tab strip */}
      <div className="flex items-center gap-1 border-b border-w-line px-3">
        {TABS.map((t) => {
          const Icon = t.icon
          const active = tab === t.key
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? 'border-w-accent text-w-accent'
                  : 'border-transparent text-w-dim hover:text-w-text'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {t.label}
            </button>
          )
        })}
      </div>

      {/* Tab content */}
      <div className="min-h-0 flex-1">
        {tab === 'chat' && <BoardChatTab projectId={projectId} />}
        {tab === 'kanban' && <ProjectKanbanBoard projectId={projectId} />}
        {tab === 'files' && <BoardFilesTab projectId={projectId} />}
      </div>
    </div>
  )
}
