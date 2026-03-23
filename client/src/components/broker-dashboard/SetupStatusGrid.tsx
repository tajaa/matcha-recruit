import { Card } from '../ui'

const statusConfig: { key: string; label: string; dot: string }[] = [
  { key: 'draft', label: 'Draft', dot: 'bg-zinc-500' },
  { key: 'invited', label: 'Invited', dot: 'bg-blue-500' },
  { key: 'activated', label: 'Active', dot: 'bg-emerald-500' },
  { key: 'expired', label: 'Expired', dot: 'bg-amber-500' },
  { key: 'cancelled', label: 'Cancelled', dot: 'bg-red-500' },
]

interface SetupStatusGridProps {
  counts: Record<string, number>
}

export function SetupStatusGrid({ counts }: SetupStatusGridProps) {
  return (
    <Card className="p-5">
      <h3 className="text-sm font-medium text-zinc-200 tracking-wide mb-4">Setup Pipeline</h3>

      <div className="space-y-2">
        {statusConfig.map(({ key, label, dot }) => {
          const count = counts[key] ?? 0
          return (
            <div key={key} className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm text-zinc-400">
                <span className={`h-2 w-2 rounded-full ${dot}`} />
                {label}
              </span>
              <span className="text-sm font-medium text-zinc-200 tabular-nums font-[Space_Grotesk]">
                {count}
              </span>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
