import type { CheckLogEntry } from '../../types/compliance'

type Props = { checkLog: CheckLogEntry[]; loading: boolean }

export function ComplianceHistoryTab({ checkLog, loading }: Props) {
  if (loading) return <p className="text-sm text-zinc-500">Loading check history...</p>

  if (checkLog.length === 0) {
    return (
      <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
        <p className="text-sm text-zinc-600">No compliance checks run yet for this location.</p>
      </div>
    )
  }

  return (
    <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800/60">
      {checkLog.map((entry) => (
        <div key={entry.id} className="px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${
                entry.status === 'completed' ? 'bg-emerald-400'
                : entry.status === 'failed' ? 'bg-red-400'
                : 'bg-amber-400 animate-pulse'
              }`} />
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                {entry.check_type}
              </span>
              <span className="text-sm text-zinc-200">{entry.status}</span>
            </div>
            <span className="text-[11px] text-zinc-600">
              {new Date(entry.started_at).toLocaleString()}
            </span>
          </div>
          {entry.status === 'completed' && (
            <div className="flex items-center gap-3 mt-1.5">
              <span className="text-[11px] text-zinc-500">{entry.new_count} new</span>
              <span className="text-[11px] text-zinc-500">{entry.updated_count} updated</span>
              <span className="text-[11px] text-zinc-500">{entry.alert_count} alerts</span>
              {entry.completed_at && (
                <span className="text-[11px] text-zinc-600">
                  Completed {new Date(entry.completed_at).toLocaleString()}
                </span>
              )}
            </div>
          )}
          {entry.error_message && (
            <p className="text-xs text-red-400 mt-1">{entry.error_message}</p>
          )}
        </div>
      ))}
    </div>
  )
}
