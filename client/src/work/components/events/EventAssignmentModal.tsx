import { useEffect, useMemo, useState } from 'react'
import { Loader2, Send, X } from 'lucide-react'
import { listChannels, getChannel, type ChannelMember, type ChannelSummary } from '../../api/channels'
import { createEventAssignment, type EmsEvent, type EmsEventAssignment } from '../../api/events'

interface EventAssignmentModalProps {
  event: EmsEvent
  onClose: () => void
  onCreated: (assignment: EmsEventAssignment) => void
}

export default function EventAssignmentModal({ event, onClose, onCreated }: EventAssignmentModalProps) {
  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [members, setMembers] = useState<ChannelMember[]>([])
  const [channelId, setChannelId] = useState('')
  const [assigneeId, setAssigneeId] = useState('')
  const [title, setTitle] = useState(event.title || 'Follow up on event')
  const [instructions, setInstructions] = useState('')
  const [dueAt, setDueAt] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadingMembers, setLoadingMembers] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listChannels({ scope: 'operations' })
      .then((rows) => setChannels(rows.filter((channel) => channel.is_member)))
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Could not load channels.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!channelId) {
      setMembers([])
      setAssigneeId('')
      return
    }
    setLoadingMembers(true)
    setAssigneeId('')
    getChannel(channelId)
      .then((channel) => setMembers(channel.members))
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : 'Could not load channel members.'))
      .finally(() => setLoadingMembers(false))
  }, [channelId])

  const selectedChannel = useMemo(() => channels.find((channel) => channel.id === channelId), [channels, channelId])

  async function submit() {
    if (!channelId || !assigneeId || !title.trim()) {
      setError('Choose a channel, teammate, and title.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const assignment = await createEventAssignment(event.id, {
        channel_id: channelId,
        assignee_user_id: assigneeId,
        shared_title: title.trim(),
        instructions: instructions.trim() || undefined,
        due_at: dueAt ? new Date(dueAt).toISOString() : undefined,
        client_request_id: crypto.randomUUID(),
      })
      onCreated(assignment)
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'Could not assign this event.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-xl border border-w-line bg-w-bg p-5 shadow-2xl" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-w-text">Assign event to a channel</h2>
            <p className="mt-1 text-xs text-w-dim">The shared title and instructions will be visible to everyone in the channel.</p>
          </div>
          <button onClick={onClose} className="rounded p-1 text-w-dim hover:bg-w-surface2 hover:text-w-text" aria-label="Close"><X size={18} /></button>
        </div>

        {loading ? <div className="flex justify-center py-10"><Loader2 className="animate-spin text-w-dim" /></div> : (
          <div className="mt-5 space-y-4">
            <label className="block text-xs text-w-dim">Channel
              <select value={channelId} onChange={(e) => setChannelId(e.target.value)} className="mt-1 w-full rounded-lg border border-w-line bg-w-surface px-3 py-2 text-sm text-w-text outline-none focus:border-w-accent/50">
                <option value="">Select a joined channel</option>
                {channels.map((channel) => <option key={channel.id} value={channel.id}>#{channel.name}</option>)}
              </select>
            </label>
            <label className="block text-xs text-w-dim">Teammate
              <select value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)} disabled={!channelId || loadingMembers} className="mt-1 w-full rounded-lg border border-w-line bg-w-surface px-3 py-2 text-sm text-w-text outline-none focus:border-w-accent/50 disabled:opacity-50">
                <option value="">{loadingMembers ? 'Loading members…' : 'Select a teammate'}</option>
                {members.map((member) => <option key={member.user_id} value={member.user_id}>{member.name} · {member.email}</option>)}
              </select>
            </label>
            <label className="block text-xs text-w-dim">Shared title
              <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} className="mt-1 w-full rounded-lg border border-w-line bg-w-surface px-3 py-2 text-sm text-w-text outline-none focus:border-w-accent/50" />
            </label>
            <label className="block text-xs text-w-dim">Instructions
              <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} maxLength={4000} rows={3} placeholder="Lisa, can you complete this by EOD?" className="mt-1 w-full resize-y rounded-lg border border-w-line bg-w-surface px-3 py-2 text-sm text-w-text outline-none focus:border-w-accent/50" />
            </label>
            <label className="block text-xs text-w-dim">Due date (optional)
              <input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} className="mt-1 rounded-lg border border-w-line bg-w-surface px-3 py-2 text-sm text-w-text outline-none focus:border-w-accent/50" />
            </label>
            {selectedChannel && <p className="rounded-lg border border-w-line bg-w-surface2/50 px-3 py-2 text-xs text-w-dim">Posting to <span className="text-w-text">#{selectedChannel.name}</span> will create an event card and notify the selected teammate.</p>}
          </div>
        )}

        {error && <p className="mt-3 text-xs text-red-300">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg px-3 py-2 text-sm text-w-dim hover:bg-w-surface2 hover:text-w-text">Cancel</button>
          <button onClick={submit} disabled={saving || loading} className="inline-flex items-center gap-2 rounded-lg bg-w-accent px-3 py-2 text-sm font-medium text-black disabled:opacity-50">
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Assign to channel
          </button>
        </div>
      </div>
    </div>
  )
}
