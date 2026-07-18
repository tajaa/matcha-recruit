import { useState } from 'react'
import { CheckCircle2, ChevronRight, History, RotateCcw, X } from 'lucide-react'
import { LABEL } from '../../ui/typography'
import { HelpHint } from '../../ui/HelpHint'
import { reopenRemediation } from '../../../api/compliance/compliance'
import type { RemediationRecord } from '../../../types/compliance'
import { PANEL, HELP } from './constants'
import { humanize } from './helpers'

// ── Remediation trail — the documentation record (resolved + dismissed) ──
export function RemediationTrail({
  records, dismissedCount, onChanged,
}: { records: RemediationRecord[]; dismissedCount: number; onChanged: () => void }) {
  const [open, setOpen] = useState(false)
  if (records.length === 0 && dismissedCount === 0) return null

  const resolved = records.filter((r) => r.status === 'resolved')
  const dismissed = records.filter((r) => r.status === 'dismissed')

  return (
    <div className="pt-1">
      <button type="button" onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-300 transition-colors">
        <History className="h-3.5 w-3.5" />
        <span className={`${LABEL} flex items-center gap-1`}>Remediation history<HelpHint text={HELP.history} /></span>
        <span className="text-[11px] text-zinc-600">
          {resolved.length} resolved{dismissedCount > 0 ? ` · ${dismissedCount} dismissed` : ''}
        </span>
        <ChevronRight className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-90' : ''}`} />
      </button>
      {open && (
        <div className={`${PANEL} mt-2 divide-y divide-white/[0.06]`}>
          {records.length === 0 && (
            <p className="px-4 py-3 text-xs text-zinc-600">No resolutions recorded yet.</p>
          )}
          {[...resolved, ...dismissed].map((r) => (
            <div key={r.issue_key} className="flex items-start justify-between gap-3 px-4 py-2.5">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {r.status === 'resolved'
                    ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                    : <X className="h-3.5 w-3.5 text-zinc-500 shrink-0" />}
                  <p className="text-sm text-zinc-200 truncate">{r.title}</p>
                </div>
                <p className="text-[11px] text-zinc-500 mt-0.5">
                  {humanize(r.source)} · {r.status === 'resolved' ? 'Resolved' : 'Dismissed'}
                  {r.resolution_method ? ` via ${humanize(r.resolution_method)}` : ''}
                  {r.resolved_at ? ` · ${new Date(r.resolved_at).toLocaleDateString()}` : ''}
                  {r.resolved_by_name ? ` · ${r.resolved_by_name}` : ''}
                </p>
                {r.resolution_note && (
                  <p className="text-[11px] text-zinc-400 mt-0.5">{r.resolution_note}</p>
                )}
              </div>
              {r.status === 'dismissed' && (
                <button type="button"
                  onClick={async () => { await reopenRemediation(r.issue_key); onChanged() }}
                  className="shrink-0 inline-flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors">
                  <RotateCcw className="h-3 w-3" /> Reopen
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
