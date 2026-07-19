import { Check, Minus } from 'lucide-react'
import { type CopilotProgress as Progress } from './types'

/**
 * Progress meter for the Copilot flow.
 *
 * The Copilot conversation is open-ended, so without this the user has no way
 * to tell whether they're two exchanges from done or in an endless loop. Every
 * segment is a real gate from `services/ir_flow.close_progress` — the same
 * predicates that decide whether Close goes through — so a full bar means the
 * Close button will actually work.
 *
 * Steps that don't apply to this incident (a property-damage report never hits
 * the OSHA chain) are dropped entirely rather than shown greyed-out: the point
 * is remaining work, and a permanently-unreachable segment reads as "stuck".
 */
export function CopilotProgress({ progress }: { progress: Progress }) {
  // The server sends every step with its applicability so the payload stays
  // self-describing; only the ones that apply to this incident are rendered.
  // "Close" always applies, so this is never empty.
  const applicable = progress.steps.filter((s) => s.status !== 'not_applicable')
  const done = progress.is_complete

  return (
    <div className="mt-2.5">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] uppercase tracking-wide text-zinc-500">
          {done ? 'Complete' : 'Progress'}
        </span>
        <span className="font-mono text-[11px] tabular-nums text-zinc-400">
          {progress.completed}/{progress.total}
        </span>
      </div>

      {/* One segment per remaining gate rather than a single continuous bar —
          the user's question is "how many more things must I do", which a
          countable row of segments answers directly. */}
      <div className="flex items-center gap-1" role="list">
        {applicable.map((step) => (
          <div
            key={step.key}
            role="listitem"
            title={step.status === 'pending' && step.hint ? step.hint : step.label}
            aria-label={`${step.label}: ${step.status === 'done' ? 'done' : 'pending'}`}
            className={`h-1.5 flex-1 rounded-full transition-colors ${
              step.status === 'done'
                ? done
                  ? 'bg-emerald-400'
                  : 'bg-emerald-400/70'
                : 'bg-zinc-800'
            }`}
          />
        ))}
      </div>

      {/* Two states only: the incident is closed, or something is still
          outstanding. "Close incident" is itself a counted step, so while
          is_complete is false there is always a pending step with a hint —
          there is no third "done but not closed" state to render. */}
      <p className="text-[11px] text-zinc-600 mt-1.5 flex items-center gap-1">
        {done ? (
          <>
            <Check className="w-3 h-3 text-emerald-400/80 shrink-0" />
            Incident closed — the record is locked.
          </>
        ) : (
          <>
            <Minus className="w-3 h-3 shrink-0" />
            Next: {progress.next_step_hint}
          </>
        )}
      </p>
    </div>
  )
}
