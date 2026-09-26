import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckSquare, Clock3 } from 'lucide-react'
import { listOpenTasks, listRecentActivity, type MWActivityItem, type MWOpenTask } from '../api/matchaWork/dashboard'
import { useWorkBase } from '../routes/WorkSurfaceContext'

export function AssignedTaskList({ tasks, base }: { tasks: MWOpenTask[]; base: string }) {
  return tasks.length === 0 ? <p className="text-xs text-w-faint">No open tasks assigned to you.</p> : <div className="space-y-1">
    {tasks.map((task) => <Link key={`${task.is_subtask ? 'subtask' : 'task'}:${task.id}`} to={`${base}/projects/${task.project_id}`} className="block rounded-lg px-2 py-2 hover:bg-w-surface2">
      <span className="flex items-center gap-2 text-sm text-w-text"><CheckSquare size={13} className="text-w-accent" /><span className="truncate">{task.title}</span>{task.is_subtask && <span className="rounded bg-w-surface2 px-1.5 py-0.5 text-[10px] text-w-dim">Subtask</span>}</span>
      <span className="ml-5 block truncate text-[11px] text-w-faint">{task.is_subtask ? `${task.parent_title ?? 'Task'} · ` : ''}{task.project_title ?? 'Workspace'}{task.due_date ? ` · Due ${task.due_date}` : ''}</span>
    </Link>)}
  </div>
}

export function ActivityList({ items, base }: { items: MWActivityItem[]; base: string }) {
  return items.length === 0 ? <p className="text-xs text-w-faint">No recent activity yet.</p> : <div className="space-y-1">
    {items.map((item) => {
      const path = item.kind === 'journal' ? `${base}/journals/${item.ref_id}`
        : item.kind === 'thread' ? `${base}/${item.ref_id}`
          : `${base}/projects/${item.project_id ?? item.ref_id}`
      return <Link key={`${item.kind}:${item.ref_id}`} to={path} className="flex items-center gap-2 rounded-lg px-2 py-2 text-xs text-w-dim hover:bg-w-surface2 hover:text-w-text"><Clock3 size={13} className="text-w-accent" /><span className="min-w-0 flex-1 truncate">{item.title}</span><span className="capitalize text-w-faint">{item.kind}</span></Link>
    })}
  </div>
}

export default function HomeInsights() {
  const base = useWorkBase()
  const [tasks, setTasks] = useState<MWOpenTask[]>([])
  const [activity, setActivity] = useState<MWActivityItem[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    void Promise.allSettled([listOpenTasks(), listRecentActivity()]).then(([taskResult, activityResult]) => {
      if (!active) return
      if (taskResult.status === 'fulfilled') setTasks(taskResult.value)
      if (activityResult.status === 'fulfilled') setActivity(activityResult.value)
      if (taskResult.status === 'rejected' || activityResult.status === 'rejected') setError('Some dashboard items could not load.')
    })
    return () => { active = false }
  }, [])

  return <div className="grid gap-3 md:grid-cols-2">
    <section className="rounded-xl border border-w-line bg-w-surface p-4"><h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-w-dim">Assigned to me</h2><AssignedTaskList tasks={tasks} base={base} /></section>
    <section className="rounded-xl border border-w-line bg-w-surface p-4"><h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-w-dim">Recent activity</h2><ActivityList items={activity} base={base} /></section>
    {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
  </div>
}
