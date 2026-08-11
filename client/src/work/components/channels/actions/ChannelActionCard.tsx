import { Check, CircleX, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { confirmEventDraft, rejectEventDraft } from '../../../api/events'

interface ChannelActionCardProps {
  action: NonNullable<NonNullable<import('../../../api/channels').ChannelMessage['metadata']>['action']>
}

export default function ChannelActionCard({ action }: ChannelActionCardProps) {
  const [status, setStatus] = useState(action.status ?? 'pending')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setStatus(action.status ?? 'pending')
  }, [action.status])

  if (action.kind !== 'event_draft') return null

  const decide = async (decision: 'confirm' | 'reject') => {
    setBusy(true)
    setError(null)
    try {
      if (decision === 'confirm') await confirmEventDraft(action.id)
      else await rejectEventDraft(action.id, { reason: 'Rejected in channel' })
      setStatus(decision === 'confirm' ? 'confirmed' : 'rejected')
    } catch (err: any) {
      const message = (err?.body as any)?.detail || err?.message || 'Action could not be completed.'
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const finished = status !== 'pending'
  return (
    <div className="mt-2 w-full max-w-sm rounded-lg border border-w-line bg-w-surface2/60 p-2.5 text-left">
      <div className="text-[11px] font-medium text-w-text">Event action</div>
      <div className="mt-1 text-[11px] text-w-dim">
        {finished ? (status === 'confirmed' ? 'Added to Events.' : 'Left out of Events.') : 'Please confirm whether Huume should add this to Events.'}
      </div>
      {!finished && (
        <div className="mt-2 flex gap-1.5">
          <button
            type="button"
            disabled={busy}
            onClick={() => decide('confirm')}
            className="inline-flex items-center gap-1 rounded bg-w-accent px-2 py-1 text-[11px] font-medium text-black disabled:opacity-50"
          >
            {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
            Add event
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => decide('reject')}
            className="inline-flex items-center gap-1 rounded border border-w-line px-2 py-1 text-[11px] text-w-dim hover:text-w-text disabled:opacity-50"
          >
            <CircleX size={12} />
            Not an event
          </button>
        </div>
      )}
      {error && <div className="mt-1 text-[11px] text-red-300">{error}</div>}
    </div>
  )
}
