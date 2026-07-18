import { HelpHint } from '../HelpHint'
import { LABEL } from '../../ui/typography'
import type { BrokerHandbookCoverage } from '../../../types/broker'

const PANEL = 'rounded-2xl border border-white/[0.06] bg-zinc-950 p-5'

const dotColors: Record<string, string> = {
  Strong: 'bg-zinc-300',
  Moderate: 'bg-zinc-500',
  Weak: 'bg-zinc-700',
}

const textColors: Record<string, string> = {
  Strong: 'text-zinc-100',
  Moderate: 'text-zinc-400',
  Weak: 'text-zinc-600',
}

interface HandbookCoverageListProps {
  handbooks: BrokerHandbookCoverage[]
}

export function HandbookCoverageList({ handbooks }: HandbookCoverageListProps) {
  if (handbooks.length === 0) {
    return (
      <div className={PANEL}>
        <h3 className={`${LABEL} mb-4 flex items-center gap-1.5 normal-case`}>Handbook Coverage <HelpHint text="How complete each client's handbook is. Thin coverage is real EPL exposure — and a concrete remediation you can sell ahead of renewal." /></h3>
        <p className="text-sm text-zinc-500">No handbooks found across your clients.</p>
      </div>
    )
  }

  return (
    <div className={PANEL}>
      <h3 className={`${LABEL} mb-4`}>Handbook Coverage</h3>

      <div className="space-y-3">
        {handbooks.map((h) => (
          <div key={h.handbook_id} className="flex items-center gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm text-zinc-200 truncate">{h.company_name}</span>
                <span className="text-[11px] text-zinc-500 truncate">{h.handbook_title}</span>
              </div>
              <div className="h-1.5 rounded-full bg-white/[0.06]">
                <div
                  className={`h-1.5 rounded-full transition-all duration-500 ${dotColors[h.strength_label] ?? 'bg-zinc-600'}`}
                  style={{ width: `${h.strength_score}%` }}
                />
              </div>
            </div>

            <div className="flex items-center gap-3 flex-shrink-0">
              <span className={`font-mono text-sm font-medium tabular-nums ${textColors[h.strength_label] ?? 'text-zinc-400'}`}>
                {h.strength_score}%
              </span>
              {h.missing_section_count > 0 && (
                <span className="text-[11px] text-zinc-500">
                  {h.missing_section_count} missing
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
