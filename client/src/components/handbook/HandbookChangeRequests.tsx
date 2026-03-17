import { Button, Card, Badge } from '../ui'
import type { HandbookChangeRequest } from '../../types/handbook'

type Props = {
  changes: HandbookChangeRequest[]
  onAccept: (changeId: string) => Promise<void>
  onReject: (changeId: string) => Promise<void>
  onJumpToSection: (sectionKey: string) => void
  loadingId: string | null
}

export function HandbookChangeRequests({ changes, onAccept, onReject, onJumpToSection, loadingId }: Props) {
  const pending = changes.filter((c) => c.status === 'pending')

  if (pending.length === 0) {
    return (
      <Card>
        <h3 className="text-sm font-semibold text-zinc-300 mb-2">Pending Changes</h3>
        <p className="text-xs text-zinc-600">No pending change requests.</p>
      </Card>
    )
  }

  return (
    <Card>
      <h3 className="text-sm font-semibold text-zinc-300 mb-3">
        Pending Changes <Badge variant="warning" className="ml-2">{pending.length}</Badge>
      </h3>
      <div className="space-y-3">
        {pending.map((c) => (
          <div key={c.id} className="border border-zinc-800 rounded-lg p-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                {c.section_key && (
                  <button
                    type="button"
                    onClick={() => onJumpToSection(c.section_key!)}
                    className="text-xs text-emerald-400 hover:underline truncate"
                  >
                    {c.section_key}
                  </button>
                )}
                {c.effective_date && (
                  <span className="text-[11px] text-zinc-500">Effective {c.effective_date}</span>
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => onAccept(c.id)}
                  disabled={loadingId === c.id}
                >
                  Accept
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => onReject(c.id)}
                  disabled={loadingId === c.id}
                >
                  Reject
                </Button>
              </div>
            </div>
            {c.rationale && <p className="text-xs text-zinc-400">{c.rationale}</p>}
            <div className="grid grid-cols-2 gap-2 text-xs">
              {c.old_content && (
                <div>
                  <p className="text-zinc-500 mb-1 font-medium">Current</p>
                  <pre className="whitespace-pre-wrap text-zinc-500 bg-zinc-900 rounded p-2 max-h-32 overflow-y-auto">
                    {c.old_content}
                  </pre>
                </div>
              )}
              <div>
                <p className="text-zinc-400 mb-1 font-medium">Proposed</p>
                <pre className="whitespace-pre-wrap text-zinc-300 bg-zinc-900 rounded p-2 max-h-32 overflow-y-auto">
                  {c.proposed_content}
                </pre>
              </div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
