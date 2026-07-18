import { useState } from 'react'
import { Plus, Loader2, Search } from 'lucide-react'
import type { ResearchTask } from '../../types'
import { useToast } from '../../../components/ui'
import { createResearchTask, getProjectDetail } from '../../api/matchaWork'
import type { Props } from './ResearchPanel/types'
import TaskCard from './ResearchPanel/TaskCard'

export default function ResearchPanel({ project, projectId, onUpdate }: Props) {
  const { toast } = useToast()
  const tasks: ResearchTask[] = (project.project_data?.research_tasks as ResearchTask[] | undefined) ?? []
  const [expandedTask, setExpandedTask] = useState<string | null>(tasks[0]?.id ?? null)
  const [creating, setCreating] = useState(false)

  // No polling needed — streaming SSE provides real-time updates

  async function handleCreateTask() {
    setCreating(true)
    try {
      const task = await createResearchTask(projectId, {
        name: 'New Research',
        instructions: '',
      })
      const updated = await getProjectDetail(projectId)
      onUpdate(updated)
      setExpandedTask(task.id)
      toast('Research task created')
    } catch {
      toast('Failed to create task', 'error')
    }
    setCreating(false)
  }

  return (
    <div className="flex-1 overflow-y-auto" style={{ background: '#1e1e1e' }}>
      <div className="px-4 py-3 flex items-center justify-between" style={{ borderBottom: '1px solid #333' }}>
        <div className="flex items-center gap-2">
          <Search size={14} style={{ color: '#ce9178' }} />
          <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#6a737d' }}>
            Research Tasks ({tasks.length})
          </span>
        </div>
        <button
          onClick={handleCreateTask}
          disabled={creating}
          className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded transition-colors"
          style={{ color: '#ce9178' }}
        >
          {creating ? <Loader2 size={10} className="animate-spin" /> : <Plus size={10} />}
          New Task
        </button>
      </div>

      {tasks.length === 0 && (
        <div className="text-center py-12" style={{ color: '#6a737d' }}>
          <Search size={24} className="mx-auto mb-2 opacity-40" />
          <p className="text-xs">No research tasks yet.</p>
          <p className="text-xs mt-1">Create a task to start extracting data from URLs.</p>
        </div>
      )}

      {tasks.map(task => (
        <TaskCard
          key={task.id}
          task={task}
          projectId={projectId}
          expanded={expandedTask === task.id}
          onToggle={() => setExpandedTask(expandedTask === task.id ? null : task.id)}
          onUpdate={onUpdate}
        />
      ))}
    </div>
  )
}
