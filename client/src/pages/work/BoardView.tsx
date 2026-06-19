import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { getProjectDetail } from '../../api/matchaWork'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import ProjectKanbanBoard from '../../components/work/ProjectKanbanBoard'

// A werk-lite "Board" is a matcha-work project under the hood, rendering the
// collaborative 5-column kanban. Thin page: resolves the project title for the
// header, then mounts the board full-pane.
export default function BoardView() {
  const { projectId } = useParams<{ projectId: string }>()
  const base = useWorkBase()

  const [title, setTitle] = useState<string | null>(null)
  const [titleLoading, setTitleLoading] = useState(true)

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
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-zinc-950 text-center">
        <p className="text-sm text-zinc-400">No board selected.</p>
        <Link
          to={`${base}`}
          className="text-sm font-medium text-emerald-400 hover:text-emerald-300"
        >
          Back to boards
        </Link>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-zinc-950">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-zinc-800 px-4 py-3">
        <Link
          to={`${base}`}
          className="shrink-0 text-zinc-400 transition-colors hover:text-zinc-200"
          title="Back to boards"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <h1 className="flex items-center gap-2 truncate text-lg font-semibold text-zinc-100">
          {title ?? (titleLoading ? <Loader2 className="h-4 w-4 animate-spin text-zinc-500" /> : 'Board')}
        </h1>
      </div>

      {/* Board */}
      <div className="min-h-0 flex-1">
        <ProjectKanbanBoard projectId={projectId} />
      </div>
    </div>
  )
}
