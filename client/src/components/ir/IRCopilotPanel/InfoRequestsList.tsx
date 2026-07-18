import { Badge } from '../../ui'
import { type useCopilotPanel } from './useCopilotPanel'

type InfoRequests = ReturnType<typeof useCopilotPanel>['infoRequests']

interface InfoRequestsListProps {
  infoRequests: InfoRequests
  onResend: (requestId: string) => void
  onRevoke: (requestId: string) => void
}

export function InfoRequestsList({ infoRequests, onResend, onRevoke }: InfoRequestsListProps) {
  if (infoRequests.length === 0) return null
  return (
    <div className="mb-4 max-w-[65ch] rounded-lg border border-white/[0.08] bg-zinc-900/60 divide-y divide-white/[0.06]">
      {infoRequests.map((r) => (
        <div key={r.id} className="px-3 py-2 text-sm">
          <div className="flex items-center gap-2">
            <Badge variant={r.status === 'submitted' ? 'success' : r.status === 'pending' ? 'warning' : 'neutral'}>
              {r.status}
            </Badge>
            <span className="flex-1 min-w-0 truncate text-zinc-300">
              {r.recipient_name} <span className="text-zinc-600">·</span> {r.recipient_email}
            </span>
            {(r.status === 'pending' || r.status === 'expired') && (
              <>
                <button
                  onClick={() => { onResend(r.id) }}
                  className="text-xs text-emerald-400 hover:text-emerald-300 shrink-0"
                >
                  Resend
                </button>
                <button
                  onClick={() => { onRevoke(r.id) }}
                  className="text-xs text-zinc-500 hover:text-red-400 shrink-0"
                >
                  Revoke
                </button>
              </>
            )}
          </div>
          {r.status === 'submitted' && r.responses && r.responses.length > 0 && (
            <div className="mt-2 space-y-1.5 border-l-2 border-sky-500/30 pl-3">
              {r.responses.map((resp, i) => (
                <div key={i}>
                  <div className="text-[11px] text-zinc-500">{resp.question}</div>
                  <div className="text-zinc-200">{resp.answer}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
