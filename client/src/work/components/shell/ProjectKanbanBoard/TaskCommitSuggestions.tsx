import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../../../../api/client'
import {
  acceptCommitSuggestion, dismissCommitSuggestion, listCommitCompletions, listCommitSuggestions,
} from '../../../api/matchaWork'
import type { CommitSuggestion } from '../../../api/matchaWork'

// onResolved reports the task's remaining pending count as distinct subtasks,
// matching the board badge (several suggestions can target one subtask).
interface Props { projectId: string; taskId: string; canEdit: boolean; onAccepted: () => void; onResolved: (pendingSubtasks: number) => void }

export default function TaskCommitSuggestions({ projectId, taskId, canEdit, onAccepted, onResolved }: Props) {
  const [pending, setPending] = useState<CommitSuggestion[]>([])
  const [accepted, setAccepted] = useState<CommitSuggestion[]>([])
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    const [pendingRows, acceptedRows] = await Promise.all([
      listCommitSuggestions(projectId, taskId), listCommitCompletions(projectId, taskId),
    ])
    setPending(pendingRows)
    setAccepted(acceptedRows)
    return pendingRows
  }, [projectId, taskId])

  useEffect(() => { queueMicrotask(() => { void refresh().catch(() => { /* commit suggestions are optional for board readers */ }) }) }, [refresh])

  async function resolve(suggestion: CommitSuggestion, kind: 'accept' | 'dismiss') {
    setPending((rows) => rows.filter((row) => row.id !== suggestion.id))
    try {
      if (kind === 'accept') {
        await acceptCommitSuggestion(projectId, suggestion.id)
        onAccepted()
      } else await dismissCommitSuggestion(projectId, suggestion.id)
      const rows = await refresh()
      onResolved(new Set(rows.map((row) => row.subtask_id)).size)
    } catch (cause) {
      await refresh().catch(() => {})
      if (!(cause instanceof ApiError && cause.status === 404)) setError(cause instanceof Error ? cause.message : 'Could not resolve suggestion.')
    }
  }

  if (!pending.length && !accepted.length && !error) return null
  return <section className="space-y-2 rounded border border-w-line p-2 text-xs text-w-text">
    <h3 className="font-semibold">Commit matches</h3>
    {error && <p role="alert" className="text-orange-400">{error}</p>}
    {pending.map((item) => <div key={item.id} className="rounded bg-w-surface2 p-2">
      <p>{item.commit_short_sha} · {item.commit_message}</p>
      {item.reasoning && <p className="text-w-dim">{item.reasoning}</p>}
      {canEdit && <div className="mt-1 flex gap-3"><button onClick={() => void resolve(item, 'accept')} className="text-w-accent">Accept for checklist</button><button onClick={() => void resolve(item, 'dismiss')} className="text-w-dim">Dismiss</button></div>}
    </div>)}
    {accepted.map((item) => <p key={item.id} className="text-w-dim">✓ {item.commit_short_sha} completed a checklist item · {item.commit_message}</p>)}
  </section>
}
