import { Check, CircleX, Loader2, X } from 'lucide-react'
import { useState } from 'react'
import { confirmEventDraft, rejectEventDraft, resolveEvent } from '../../../api/events'
import type { ChannelAction } from '../../../api/channelActions'

interface ChannelActionsDrawerProps {
  open: boolean
  actions: ChannelAction[]
  loading: boolean
  onClose: () => void
  onRefresh: () => Promise<void>
}

export default function ChannelActionsDrawer({ open, actions, loading, onClose, onRefresh }: ChannelActionsDrawerProps) {
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  if (!open) return null

  async function decide(action: ChannelAction, decision: 'confirm' | 'reject' | 'completed' | 'no_action') {
    setBusyId(action.id)
    setError(null)
    try {
      if (action.kind === 'event_draft') {
        if (decision === 'confirm') await confirmEventDraft(action.id)
        if (decision === 'reject') await rejectEventDraft(action.id)
      } else if (action.kind === 'event' && (decision === 'completed' || decision === 'no_action')) {
        await resolveEvent(action.id, { resolution: decision })
      }
      await onRefresh()
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'Action could not be completed.')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={onClose}>
      <aside className="h-full w-full max-w-md overflow-y-auto border-l border-w-line bg-w-bg p-4 shadow-2xl" onClick={(event) => event.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <div><h2 className="font-semibold text-w-text">Channel actions</h2><p className="text-xs text-w-dim">Open events and drafts in this channel.</p></div>
          <button onClick={onClose} className="rounded p-1.5 text-w-dim hover:bg-w-surface2 hover:text-w-text" aria-label="Close actions"><X size={18} /></button>
        </div>
        {loading ? <Loader2 className="mx-auto mt-10 animate-spin text-w-dim" /> : actions.length === 0 ? (
          <p className="mt-10 text-center text-sm text-w-dim">No open actions.</p>
        ) : (
          <div className="space-y-3">
            {actions.map((action) => (
              <section key={`${action.kind}:${action.id}`} className="rounded-lg border border-w-line bg-w-surface p-3">
                <div className="text-sm font-medium text-w-text">{action.title}</div>
                <p className="mt-1 text-xs text-w-dim">{action.summary}</p>
                {action.allowed_actions.length > 0 && <div className="mt-3 flex flex-wrap gap-2">
                  {action.allowed_actions.includes('confirm') && <button disabled={busyId === action.id} onClick={() => decide(action, 'confirm')} className="inline-flex items-center gap-1 rounded bg-w-accent px-2 py-1 text-xs font-medium text-black disabled:opacity-50"><Check size={12} /> Add event</button>}
                  {action.allowed_actions.includes('reject') && <button disabled={busyId === action.id} onClick={() => decide(action, 'reject')} className="inline-flex items-center gap-1 rounded border border-w-line px-2 py-1 text-xs text-w-dim disabled:opacity-50"><CircleX size={12} /> Not an event</button>}
                  {action.allowed_actions.includes('complete') && <button disabled={busyId === action.id} onClick={() => decide(action, 'completed')} className="rounded border border-emerald-500/40 px-2 py-1 text-xs text-emerald-300 disabled:opacity-50">Complete</button>}
                  {action.allowed_actions.includes('no_action') && <button disabled={busyId === action.id} onClick={() => decide(action, 'no_action')} className="rounded border border-w-line px-2 py-1 text-xs text-w-dim disabled:opacity-50">No action</button>}
                </div>}
              </section>
            ))}
          </div>
        )}
        {error && <p className="mt-3 text-xs text-red-300">{error}</p>}
      </aside>
    </div>
  )
}
