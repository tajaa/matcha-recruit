import type { MWProjectTask } from '../../types/matchaWork'

interface TaskProgressBarProps {
  tasks: MWProjectTask[]
}

export default function TaskProgressBar({ tasks }: TaskProgressBarProps) {
  const total = tasks.length
  const done = tasks.filter((t) => t.status === 'completed').length
  const pct = total > 0 ? Math.round((done / total) * 100) : 0

  if (total === 0) {
    return <p className="px-3 py-1 text-[9px] font-medium text-white/40">0 tasks</p>
  }

  return (
    <div className="flex items-center gap-2 px-3 py-1">
      <div className="h-1 flex-1 overflow-hidden rounded-sm bg-w-surface2">
        <div
          className="h-full rounded-sm bg-w-accent transition-[width] duration-300 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="shrink-0 text-[9px] font-medium text-white/55">
        {done} / {total} · {pct}%
      </span>
    </div>
  )
}
