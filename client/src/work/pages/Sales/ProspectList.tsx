import { AlertTriangle } from 'lucide-react'
import type { SalesProspect } from '../../api/matchaWork/sales'
import { FIT_LABEL, MAX_BATCH, SEGMENT_LABEL, STATUS_LABEL, sendable } from './salesLogic'

/** The campaign's prospects, most in need of the person first. Drafts can be
 *  ticked (up to a batch) for review and sending. */
export default function ProspectList({ prospects, consulting, selected, openId, onToggle, onOpen }: {
  prospects: SalesProspect[]
  consulting: boolean
  selected: Set<string>
  openId: string | null
  onToggle: (prospect: SalesProspect) => void
  onOpen: (prospect: SalesProspect) => void
}) {
  if (!prospects.length) {
    return <p className="px-1 py-6 text-center text-xs text-w-dim">No prospects yet. Import a list, or ask Espresso to find and research them.</p>
  }
  const full = selected.size >= MAX_BATCH
  return (
    <ul className="divide-y divide-w-line rounded-lg border border-w-line">
      {prospects.map((p) => {
        const flags = p.review_flags ?? []
        const canSend = sendable(p)
        const who = p.name || p.company || p.email || p.website
        return (
          <li key={p.id} className={`flex items-start gap-2 px-3 py-2 ${openId === p.id ? 'bg-w-surface2/60' : ''}`}>
            <input
              type="checkbox"
              aria-label={`Select ${who}`}
              checked={selected.has(p.id)}
              disabled={!canSend || (full && !selected.has(p.id))}
              onChange={() => onToggle(p)}
              className="mt-1"
            />
            <button type="button" onClick={() => onOpen(p)} className="min-w-0 flex-1 text-left">
              <span className="flex items-center gap-2">
                <span className="truncate text-xs font-semibold text-w-text">{who}</span>
                {p.name && p.company && <span className="truncate text-[11px] text-w-dim">{p.company}</span>}
                <span className="ml-auto shrink-0 text-[10px] text-w-dim">{STATUS_LABEL[p.status]}</span>
              </span>
              {consulting && (p.signal || p.segment || p.fit) && (
                <span className="mt-0.5 block truncate text-[11px] text-w-dim">
                  {[p.fit ? FIT_LABEL[p.fit] : '', p.segment ? SEGMENT_LABEL[p.segment] : '', p.signal].filter(Boolean).join(' · ')}
                </span>
              )}
              {p.subject && <span className="mt-0.5 block truncate text-[11px] text-w-faint">{p.subject}</span>}
              {flags.length > 0 && (
                <span className="mt-0.5 flex items-center gap-1 text-[11px] text-amber-400">
                  <AlertTriangle size={11} />{flags.length === 1 ? '1 thing to check' : `${flags.length} things to check`}
                </span>
              )}
              {p.error && <span className="mt-0.5 block text-[11px] text-red-400">{p.error}</span>}
            </button>
          </li>
        )
      })}
    </ul>
  )
}
