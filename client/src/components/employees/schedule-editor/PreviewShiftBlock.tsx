import type { CSSProperties } from 'react'
import { AlertTriangle } from 'lucide-react'
import { fmtTime } from '../../../types/employeeSchedule'
import type { PreviewShift } from '../schedule-pilot/reviewVerdict'

/** A proposed shift drawn on the board before anything is written.
 *
 *  Read-only on purpose: no drag handle, no resize, no drop target, no Huume
 *  toggle. It is a picture of what approving would create — editing happens
 *  after approval, on the real drafts. Dashed so it never reads as a saved
 *  shift, even in a screenshot. */
export default function PreviewShiftBlock({ shift, style }: { shift: PreviewShift; style: CSSProperties }) {
  const filled = shift.names.length
  const label = `Proposed ${shift.role} ${fmtTime(shift.starts_at)}–${fmtTime(shift.ends_at)}: `
    + `${filled ? shift.names.join(', ') : 'nobody'}${shift.open ? `, ${shift.open} open` : ''}`
  return (
    <div
      style={style}
      role="img"
      aria-label={label}
      title={shift.reasons.length ? shift.reasons.join('\n') : undefined}
      className={`pointer-events-auto absolute z-10 min-w-0 overflow-hidden rounded-md border border-dashed p-1.5 ${shift.open ? 'border-amber-400/60 bg-amber-500/[0.07]' : 'border-emerald-400/60 bg-emerald-500/[0.07]'}`}
    >
      <div className="flex items-start gap-1">
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[11px] font-medium text-zinc-100">{shift.role}</span>
          <span className="block truncate text-[10px] text-zinc-500">{fmtTime(shift.starts_at)}–{fmtTime(shift.ends_at)}</span>
        </span>
        {shift.warn && <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-400" aria-hidden />}
      </div>
      <div className="mt-1 space-y-0.5">
        {shift.names.map((name, index) => (
          <span key={`${index}-${name}`} className="block truncate rounded bg-emerald-500/10 px-1 text-[10px] text-emerald-100">{name}</span>
        ))}
        {Array.from({ length: shift.open }, (_, index) => (
          <span key={`open-${index}`} className="block truncate rounded border border-dashed border-amber-400/60 px-1 text-[10px] italic text-amber-200">open</span>
        ))}
      </div>
    </div>
  )
}
