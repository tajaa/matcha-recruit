import { AlertTriangle } from 'lucide-react'
import { type CopilotEvidence } from './types'

/**
 * Preponderance-of-evidence tracker for the Copilot flow. Mirrors the ER
 * Copilot's evidence-confidence banner (`ERGuidancePanel`'s "Evidence
 * Confidence" meter) applied to incident reporting: `close_progress` /
 * `CopilotProgress` answers "what does the law require to close this
 * incident", this answers "how well-documented is the record" — a report
 * can clear every close gate while still having no photos, no witnesses,
 * and no logged corrective action.
 *
 * The days-open line is the other half of the brief: visibility into how
 * long this has been running, so an investigation can't drift open
 * indefinitely unnoticed.
 */
export function EvidenceTracker({ evidence }: { evidence: CopilotEvidence }) {
  return (
    <div className="mt-2.5">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] uppercase tracking-wide text-zinc-500">Evidence</span>
        <span className="font-mono text-[11px] tabular-nums text-zinc-400">
          {evidence.score}% {evidence.sufficient ? '· sufficient' : `· needs ${evidence.threshold}%`}
        </span>
      </div>

      <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${evidence.sufficient ? 'bg-emerald-400' : 'bg-amber-400'}`}
          style={{ width: `${evidence.score}%` }}
        />
      </div>

      {evidence.missing.length > 0 && (
        <p className="text-[11px] text-zinc-600 mt-1.5">
          Missing: {evidence.missing.join(', ')}
        </p>
      )}

      <p className={`text-[11px] mt-1 flex items-center gap-1 ${evidence.is_overdue ? 'text-amber-400' : 'text-zinc-600'}`}>
        {evidence.is_overdue && <AlertTriangle className="w-3 h-3 shrink-0" />}
        {evidence.days_open} day{evidence.days_open === 1 ? '' : 's'} open
        {evidence.is_overdue
          ? ` — past the ${evidence.max_days}-day target for this severity`
          : ` (${evidence.max_days}-day target)`}
      </p>
    </div>
  )
}
