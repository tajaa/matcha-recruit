import { X } from 'lucide-react'
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
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200 rounded-xl shadow-xl p-6 w-full max-w-md">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-900">
            {sendModal.kind === 'now' ? `Send to ${stats?.active ?? 0} subscribers`
              : sendModal.kind === 'segment' ? 'Send to segment'
              : 'Schedule send'}
          </h3>
          <button onClick={() => setSendModal(null)} className="text-slate-400 hover:text-slate-700"><X size={16} /></button>
        </div>
        {sendModal.kind === 'segment' && (
          <div className="space-y-2 max-h-64 overflow-auto">
            <p className="text-xs text-slate-500 mb-2">Pick one or more tags. Leave all unchecked to send to everyone.</p>
            {tags.map((t) => (
              <label key={t.id} className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
                <input
                  type="checkbox"
                  checked={sendSegmentTags.includes(t.slug)}
                  onChange={(e) => {
                    if (e.target.checked) setSendSegmentTags((prev) => [...prev, t.slug])
                    else setSendSegmentTags((prev) => prev.filter((s) => s !== t.slug))
                  }}
                  className="accent-emerald-600"
                />
                <span className="font-mono text-slate-500">{t.slug}</span>
                <span className="text-slate-400">·</span>
                <span>{t.label}</span>
                <span className="ml-auto text-slate-400">{t.subscriber_count}</span>
              </label>
            ))}
          </div>
        )}
        {sendModal.kind === 'schedule' && (
          <div>
            <label className="block text-xs text-slate-600 mb-1">Send at</label>
            <input
              type="datetime-local"
              value={sendScheduledAt}
              onChange={(e) => setSendScheduledAt(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-slate-300 bg-white text-sm text-slate-900 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 transition-colors"
            />
            <p className="text-[10px] text-slate-400 mt-2">
              Newsletter scheduler beat must be enabled in scheduler_settings (`task_key='newsletter_scheduler'`).
            </p>
          </div>
        )}
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={() => setSendModal(null)} className="text-xs px-3 py-1.5 rounded-lg text-slate-500 hover:text-slate-800">Cancel</button>
          <button onClick={confirmSend} disabled={sending} className="text-xs px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm disabled:opacity-40">
            {sending ? 'Working…' : sendModal.kind === 'schedule' ? 'Schedule' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}
