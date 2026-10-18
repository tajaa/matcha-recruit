import { useEffect, useState } from 'react'
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { ApiError } from '../../api/client'
import { errorText } from './JobSearch/jobSearchLogic'
import { useMe } from '../../hooks/useMe'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import { getAgentTaskForSearch } from '../api/matchaWork/agentTasks'

/** Old Job search links open the search's task, preserving the named job. */
export default function JobSearchRedirect() {
  const base = useWorkBase()
  const { isPersonal, loading } = useMe()
  const { searchId } = useParams<{ searchId?: string }>()
  const [params] = useSearchParams()
  const [resolved, setResolved] = useState<{ searchId: string; taskId: string | null; error?: string } | null>(null)

  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!searchId || loading || !isPersonal) return
    let cancelled = false
    void getAgentTaskForSearch(searchId).then(
      (task) => { if (!cancelled) setResolved({ searchId, taskId: task.id }) },
      (e: unknown) => {
        if (!cancelled) setResolved({ searchId, taskId: null,
          error: e instanceof ApiError && e.status === 404 ? undefined : errorText(e, "Couldn't open this search."),
        })
      },
    )
    return () => { cancelled = true }
  }, [searchId, loading, isPersonal, attempt])

  if (!searchId || (!loading && !isPersonal)) return <Navigate to={`${base}/tasks`} replace />
  if (!resolved || resolved.searchId !== searchId) {
    return <div className="flex flex-1 items-center justify-center"><Loader2 aria-label="Opening task" className="animate-spin text-w-dim" /></div>
  }
  if (resolved.error) return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
      <p role="alert" className="text-xs text-w-dim">{resolved.error}</p>
      <button type="button" className="text-xs font-semibold text-w-accent" onClick={() => {
        setResolved(null)
        setAttempt((n) => n + 1)
      }}>Try again</button>
      <Link to={`${base}/tasks`} className="text-xs text-w-dim">All tasks</Link>
    </div>
  )
  const taskPath = resolved.taskId ? `/${encodeURIComponent(resolved.taskId)}` : ''
  const job = params.get('job')
  const item = resolved.taskId && job ? `?item=${encodeURIComponent(job)}` : ''
  return <Navigate to={`${base}/tasks${taskPath}${item}`} replace />
}
