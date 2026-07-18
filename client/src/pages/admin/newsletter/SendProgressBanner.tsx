import { Loader2 } from 'lucide-react'
import type { Progress } from './types'

export function SendProgressBanner({ progress }: { progress: Progress }) {
  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 mb-4 flex items-center gap-3">
      <Loader2 className="animate-spin text-amber-300 shrink-0" size={16} />
      <div className="flex-1">
        <div className="text-xs text-amber-200">
          Sending: {progress.sent} / {progress.queued}
          {progress.failed > 0 && <span className="ml-2 text-red-300">{progress.failed} failed</span>}
        </div>
        <div className="mt-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
          <div
            className="h-full bg-amber-400 transition-all"
            style={{ width: `${progress.queued ? Math.round((progress.sent / progress.queued) * 100) : 0}%` }}
          />
        </div>
      </div>
    </div>
  )
}
