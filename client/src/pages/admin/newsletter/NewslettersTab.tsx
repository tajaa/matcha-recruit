import { FileText, BarChart3, Trash2 } from 'lucide-react'
import { api } from '../../../api/client'
import type { Newsletter } from './types'

export function NewslettersTab({
  newsletters,
  onEdit,
  onDelete,
  onOpenAnalytics,
  onReload,
}: {
  newsletters: Newsletter[]
  onEdit: (nl: Newsletter) => void
  onDelete: (id: string) => Promise<void>
  onOpenAnalytics: (nl: Newsletter) => Promise<void>
  onReload: () => Promise<void> | void
}) {
  const drafts = newsletters.filter(n => n.status === 'draft')
  const sent = newsletters.filter(n => n.status !== 'draft')

  const NlRow = ({ nl }: { nl: Newsletter }) => (
    <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-zinc-800 hover:bg-zinc-800/20">
      <FileText size={16} className="text-zinc-500 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-zinc-200 font-medium truncate">{nl.title}</p>
        <p className="text-[11px] text-zinc-500">{nl.subject}</p>
        {nl.scheduled_at && nl.status === 'scheduled' && (
          <p className="text-[10px] text-amber-300 mt-0.5">
            Scheduled for {new Date(nl.scheduled_at).toLocaleString()}
          </p>
        )}
      </div>
      <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${
        nl.status === 'sent' ? 'bg-emerald-900/30 text-emerald-400' :
        nl.status === 'sending' ? 'bg-amber-900/30 text-amber-400' :
        nl.status === 'scheduled' ? 'bg-sky-900/30 text-sky-300' :
        'bg-zinc-800 text-zinc-400'
      }`}>{nl.status}</span>
      {nl.status === 'sent' && (
        <button onClick={() => onOpenAnalytics(nl)} className="text-zinc-500 hover:text-zinc-300 text-xs flex items-center gap-1">
          <BarChart3 size={12} /> Analytics
        </button>
      )}
      {nl.status === 'draft' && (
        <>
          <button onClick={() => onEdit(nl)} className="text-zinc-500 hover:text-emerald-400 text-xs font-medium">Edit</button>
          <button onClick={() => onDelete(nl.id)} className="text-zinc-500 hover:text-red-400"><Trash2 size={13} /></button>
        </>
      )}
      {nl.status === 'scheduled' && (
        <button
          onClick={async () => {
            await api.post(`/admin/newsletter/newsletters/${nl.id}/unschedule`, {})
            onReload()
          }}
          className="text-zinc-500 hover:text-zinc-300 text-xs"
        >
          Unschedule
        </button>
      )}
    </div>
  )

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Drafts</p>
        {drafts.length === 0
          ? <p className="text-zinc-600 text-xs py-3 text-center border border-dashed border-zinc-800 rounded-xl">No drafts — click <span className="text-zinc-400">+ New Newsletter</span> to start one.</p>
          : <div className="space-y-2">{drafts.map(nl => <NlRow key={nl.id} nl={nl} />)}</div>
        }
      </div>
      {sent.length > 0 && (
        <div>
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Sent &amp; Scheduled</p>
          <div className="space-y-2">{sent.map(nl => <NlRow key={nl.id} nl={nl} />)}</div>
        </div>
      )}
      {newsletters.length === 0 && <p className="text-zinc-500 text-sm py-8 text-center">No newsletters yet.</p>}
    </div>
  )
}
