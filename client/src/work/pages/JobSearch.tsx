import { useEffect, useState } from 'react'
import { Navigate, useParams, useSearchParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import { getAgentTaskForSearch } from '../api/matchaWork/agentTasks'

/** Old Job search links open the search's task, preserving the named job. */
export default function JobSearchRedirect() {
  const base = useWorkBase()
  const { isPersonal, loading } = useMe()
  const { searchId } = useParams<{ searchId?: string }>()
  const [params] = useSearchParams()
  const [resolved, setResolved] = useState<{ searchId: string; taskId: string | null } | null>(null)

  useEffect(() => {
    if (!searchId || loading || !isPersonal) return
    let cancelled = false
    void getAgentTaskForSearch(searchId).then(
      (task) => { if (!cancelled) setResolved({ searchId, taskId: task.id }) },
      () => { if (!cancelled) setResolved({ searchId, taskId: null }) },
    )
    return () => { cancelled = true }
  }, [searchId, loading, isPersonal])

  if (!searchId || (!loading && !isPersonal)) return <Navigate to={`${base}/tasks`} replace />
  if (!resolved || resolved.searchId !== searchId) {
    return <div className="flex flex-1 items-center justify-center"><Loader2 aria-label="Opening task" className="animate-spin text-w-dim" /></div>
  }
  const taskPath = resolved.taskId ? `/${encodeURIComponent(resolved.taskId)}` : ''
  const job = params.get('job')
  const item = resolved.taskId && job ? `?item=${encodeURIComponent(job)}` : ''
  return <Navigate to={`${base}/tasks${taskPath}${item}`} replace />
}
