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
    <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-slate-200 bg-white shadow-sm hover:bg-slate-50">
      <FileText size={16} className="text-slate-400 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-slate-800 font-medium truncate">{nl.title}</p>
        <p className="text-[11px] text-slate-400">{nl.subject}</p>
        {nl.scheduled_at && nl.status === 'scheduled' && (
          <p className="text-[10px] text-amber-600 mt-0.5">
            Scheduled for {new Date(nl.scheduled_at).toLocaleString()}
          </p>
        )}
      </div>
      <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${
        nl.status === 'sent' ? 'bg-emerald-50 text-emerald-700' :
        nl.status === 'sending' ? 'bg-amber-50 text-amber-700' :
        nl.status === 'scheduled' ? 'bg-sky-50 text-sky-700' :
        'bg-slate-100 text-slate-500'
      }`}>{nl.status}</span>
      {nl.status === 'sent' && (
        <button onClick={() => onOpenAnalytics(nl)} className="text-slate-400 hover:text-slate-700 text-xs flex items-center gap-1">
          <BarChart3 size={12} /> Analytics
        </button>
      )}
      {nl.status === 'draft' && (
        <>
          <button onClick={() => onEdit(nl)} className="text-slate-500 hover:text-emerald-700 text-xs font-medium">Edit</button>
          <button onClick={() => onDelete(nl.id)} className="text-slate-400 hover:text-red-600"><Trash2 size={13} /></button>
        </>
      )}
      {nl.status === 'scheduled' && (
        <button
          onClick={async () => {
            await api.post(`/admin/newsletter/newsletters/${nl.id}/unschedule`, {})
            onReload()
          }}
          className="text-slate-400 hover:text-slate-700 text-xs"
        >
          Unschedule
        </button>
      )}
    </div>
  )

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[10px] text-slate-400 uppercase tracking-wider mb-2">Drafts</p>
        {drafts.length === 0
          ? <p className="text-slate-400 text-xs py-3 text-center border border-dashed border-slate-300 rounded-xl">No drafts — click <span className="text-slate-600">+ New Newsletter</span> to start one.</p>
          : <div className="space-y-2">{drafts.map(nl => <NlRow key={nl.id} nl={nl} />)}</div>
        }
      </div>
      {sent.length > 0 && (
        <div>
          <p className="text-[10px] text-slate-400 uppercase tracking-wider mb-2">Sent &amp; Scheduled</p>
          <div className="space-y-2">{sent.map(nl => <NlRow key={nl.id} nl={nl} />)}</div>
        </div>
      )}
      {newsletters.length === 0 && <p className="text-slate-400 text-sm py-8 text-center">No newsletters yet.</p>}
    </div>
  )
}
