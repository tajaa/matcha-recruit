import { HelpHint } from '../HelpHint'
import { LABEL } from '../../ui/typography'

const PANEL = 'rounded-2xl border border-white/[0.06] bg-zinc-950 p-5'

const statusConfig: { key: string; label: string; dot: string }[] = [
  { key: 'draft', label: 'Draft', dot: 'bg-zinc-600' },
  { key: 'invited', label: 'Invited', dot: 'bg-zinc-700' },
  { key: 'activated', label: 'Active', dot: 'bg-zinc-500' },
  { key: 'expired', label: 'Expired', dot: 'bg-zinc-800' },
  { key: 'cancelled', label: 'Cancelled', dot: 'bg-zinc-900' },
]

const onboardingConfig: { key: string; label: string; dot: string }[] = [
  { key: 'submitted', label: 'Submitted', dot: 'bg-zinc-700' },
  { key: 'under_review', label: 'Under Review', dot: 'bg-zinc-600' },
  { key: 'configuring', label: 'Configuring', dot: 'bg-zinc-500' },
  { key: 'live', label: 'Live', dot: 'bg-zinc-300' },
]

interface SetupStatusGridProps {
  counts: Record<string, number>
}

export function SetupStatusGrid({ counts }: SetupStatusGridProps) {
  return (
    <div className={PANEL}>
      <h3 className={`${LABEL} mb-4 flex items-center gap-1.5 normal-case`}>Setup Pipeline <HelpHint text="Where your in-flight client setups sit — from draft/invited through to live — so you can chase what's stalled before it expires." /></h3>

      <div className="space-y-2">
        {statusConfig.map(({ key, label, dot }) => {
          const count = counts[key] ?? 0
          return (
            <div key={key} className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm text-zinc-400">
                <span className={`h-2 w-2 rounded-full ${dot}`} />
                {label}
              </span>
              <span className="font-mono text-sm font-medium text-zinc-200 tabular-nums">
                {count}
              </span>
            </div>
          )
        })}
      </div>

      <div className="border-t border-white/[0.06] my-4" />

      <h3 className={`${LABEL} mb-4`}>Onboarding</h3>

      <div className="space-y-2">
        {onboardingConfig.map(({ key, label, dot }) => {
          const count = counts[key] ?? 0
          return (
            <div key={key} className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm text-zinc-400">
                <span className={`h-2 w-2 rounded-full ${dot}`} />
                {label}
              </span>
              <span className="font-mono text-sm font-medium text-zinc-200 tabular-nums">
                {count}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
