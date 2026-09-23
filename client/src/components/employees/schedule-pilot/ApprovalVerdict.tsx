import { AlertTriangle, CalendarRange, CircleCheck, CircleSlash, MessageSquareText, Search, UserRound } from 'lucide-react'
import type { ApprovalVerdict as Verdict, VerdictFix, VerdictTone } from './reviewVerdict'

const TONE: Record<VerdictTone, { card: string; icon: typeof CircleCheck; iconClass: string }> = {
  ok: { card: 'border-emerald-500/30 bg-emerald-500/[0.06]', icon: CircleCheck, iconClass: 'text-emerald-400' },
  warn: { card: 'border-amber-500/30 bg-amber-500/[0.06]', icon: AlertTriangle, iconClass: 'text-amber-400' },
  bad: { card: 'border-red-500/35 bg-red-500/[0.07]', icon: CircleSlash, iconClass: 'text-red-400' },
}

const ISSUE_DOT: Record<VerdictTone, string> = {
  ok: 'bg-emerald-400', warn: 'bg-amber-400', bad: 'bg-red-400',
}

export interface ApprovalVerdictProps {
  verdict: Verdict
  onFix?(fix: VerdictFix): void
  /** A generated week can be looked at before it exists. */
  onShowWeek?(): void
  onApprove?(): void
  onCancel?(): void
  /** The thread is mid-reply: the staged state may change under the buttons. */
  decisionDisabled?: boolean
}

const FIX_LABEL: Record<VerdictFix['kind'], { label: string; icon: typeof Search }> = {
  board: { label: 'Show', icon: Search },
  person: { label: 'Show their week', icon: UserRound },
  ask: { label: 'Ask Huume', icon: MessageSquareText },
}

/** The first thing a review says: can this be approved, and if not, what is
 *  in the way — each problem with the one click that starts fixing it. */
export default function ApprovalVerdict({ verdict, onFix, onShowWeek, onApprove, onCancel, decisionDisabled }: ApprovalVerdictProps) {
  const tone = TONE[verdict.tone]
  const Icon = tone.icon
  return (
    <section className={`mt-3 rounded-lg border px-3 py-3 ${tone.card}`} aria-label="Approval verdict">
      <div className="flex items-start gap-2">
        <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone.iconClass}`} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-snug text-zinc-100">{verdict.headline}</p>
          {verdict.facts.length > 0 && (
            <p className="mt-0.5 font-mono text-[11px] tabular-nums text-zinc-400">{verdict.facts.join(' · ')}</p>
          )}
        </div>
      </div>

      {verdict.issues.length > 0 && (
        <ul className="mt-3 space-y-2" aria-label="Before you approve">
          {verdict.issues.map((issue) => {
            const fix = issue.fix ? FIX_LABEL[issue.fix.kind] : null
            const FixIcon = fix?.icon
            return (
              <li key={issue.key} className="flex items-start gap-2 text-xs">
                <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${ISSUE_DOT[issue.tone]}`} aria-hidden />
                <span className="min-w-0 flex-1 leading-snug">
                  <span className="text-zinc-100">{issue.label}</span>
                  {issue.detail && <span className="text-zinc-400"> · {issue.detail}</span>}
                </span>
                {issue.fix && fix && FixIcon && onFix && (
                  <button
                    type="button"
                    onClick={() => onFix(issue.fix as VerdictFix)}
                    className="inline-flex shrink-0 items-center gap-1 rounded border border-white/[0.08] px-1.5 py-0.5 text-[11px] text-zinc-300 hover:bg-white/[0.06] hover:text-zinc-100"
                  >
                    <FixIcon className="h-3 w-3" /> {fix.label}
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {(onShowWeek || onApprove || onCancel) && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {onShowWeek && (
            <button type="button" onClick={onShowWeek} className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.1] px-2.5 py-1.5 text-xs text-zinc-200 hover:bg-white/[0.06]">
              <CalendarRange className="h-3.5 w-3.5" /> See the week on the board
            </button>
          )}
          <span className="ml-auto flex items-center gap-2">
            {onCancel && (
              <button type="button" onClick={onCancel} disabled={decisionDisabled} className="rounded-lg border border-white/[0.1] px-2.5 py-1.5 text-xs text-zinc-300 hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-40">
                Cancel
              </button>
            )}
            {onApprove && (
              <button
                type="button"
                onClick={onApprove}
                disabled={decisionDisabled}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-40 ${verdict.tone === 'bad' ? 'border border-amber-400/50 text-amber-100 hover:bg-amber-400/10' : 'bg-emerald-500 text-zinc-950 hover:bg-emerald-400'}`}
              >
                {verdict.approveLabel}
              </button>
            )}
          </span>
        </div>
      )}
    </section>
  )
}
