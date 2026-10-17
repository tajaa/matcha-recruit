import { AdminInput, AdminButton } from '../../../../components/admin/AdminUI'
import { Modal } from '../../../../components/ui'
import type { Tag, SubStats } from './types'

export function SendModal({
  sendModal, setSendModal,
  tags, stats,
  sendSegmentTags, setSendSegmentTags,
  sendScheduledAt, setSendScheduledAt,
  sending, confirmSend,
}: {
  sendModal: { kind: 'now' | 'schedule' | 'segment' }
  setSendModal: (v: { kind: 'now' | 'schedule' | 'segment' } | null) => void
  tags: Tag[]
  stats: SubStats | null
  sendSegmentTags: string[]; setSendSegmentTags: (v: string[] | ((prev: string[]) => string[])) => void
  sendScheduledAt: string; setSendScheduledAt: (v: string) => void
  sending: boolean
  confirmSend: () => Promise<void>
}) {
  const title =
    sendModal.kind === 'now' ? `Send to ${stats?.active ?? 0} subscribers`
      : sendModal.kind === 'segment' ? 'Send to segment'
      : 'Schedule send'

  return (
    <Modal open onClose={() => setSendModal(null)} title={title} width="sm" dismissible={!sending}>
        {sendModal.kind === 'segment' && (
          <div className="space-y-2 max-h-64 overflow-auto">
            <p className="text-xs text-zinc-500 mb-2">Pick one or more tags. Leave all unchecked to send to everyone.</p>
            {tags.map((t) => (
              <label key={t.id} className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={sendSegmentTags.includes(t.slug)}
                  onChange={(e) => {
                    if (e.target.checked) setSendSegmentTags((prev) => [...prev, t.slug])
                    else setSendSegmentTags((prev) => prev.filter((s) => s !== t.slug))
                  }}
                  className="accent-emerald-500"
                />
                <span className="font-mono text-zinc-400">{t.slug}</span>
                <span className="text-zinc-500">·</span>
                <span>{t.label}</span>
                <span className="ml-auto text-zinc-600">{t.subscriber_count}</span>
              </label>
            ))}
          </div>
        )}
        {sendModal.kind === 'schedule' && (
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Send at</label>
            <AdminInput
              type="datetime-local"
              value={sendScheduledAt}
              onChange={(e) => setSendScheduledAt(e.target.value)}
            />
            <p className="text-[10px] text-zinc-500 mt-2">
              Newsletter scheduler beat must be enabled in scheduler_settings (`task_key='newsletter_scheduler'`).
            </p>
          </div>
        )}
      <div className="flex justify-end gap-2 mt-5">
        <button onClick={() => setSendModal(null)} className="text-xs px-3 py-1.5 rounded-lg text-zinc-400 hover:text-zinc-200">Cancel</button>
        <AdminButton onClick={confirmSend} disabled={sending} className="disabled:opacity-40" variant="success">
          {sending ? 'Working…' : sendModal.kind === 'schedule' ? 'Schedule' : 'Send'}
        </AdminButton>
      </div>
    </Modal>
  )
}
