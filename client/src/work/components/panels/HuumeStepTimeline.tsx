import { CheckCircle2, XCircle, Clock, FileSearch, Bot } from 'lucide-react'
import type { HuumeStep } from '../../types'

const KIND_ICON: Record<HuumeStep['kind'], typeof FileSearch> = {
  read: FileSearch,
  staged: Clock,
  write: Bot,
  finish: CheckCircle2,
}

function statusColor(status: HuumeStep['status'], lm?: boolean) {
  switch (status) {
    case 'ok':
      return lm ? 'text-emerald-700 border-emerald-300 bg-emerald-50' : 'text-emerald-300 border-emerald-800 bg-emerald-950/40'
    case 'rejected':
      return lm ? 'text-amber-700 border-amber-300 bg-amber-50' : 'text-amber-300 border-amber-800 bg-amber-950/40'
    case 'error':
      return lm ? 'text-red-700 border-red-300 bg-red-50' : 'text-red-300 border-red-800 bg-red-950/40'
    default:
      return lm ? 'text-zinc-500 border-zinc-300 bg-zinc-50' : 'text-zinc-400 border-zinc-700 bg-zinc-800/40'
  }
}

/** Huume's per-turn tool-call timeline — rendered under an assistant bubble
 * from `message.metadata.huume_steps` (persisted so it survives reload,
 * matching how HR Pilot citations persist on message metadata). */
export default function HuumeStepTimeline({ steps, lightMode }: { steps: HuumeStep[]; lightMode?: boolean }) {
  if (!steps || steps.length === 0) return null
  return (
    <div className="mt-2.5 space-y-1 border-t pt-2" style={{ borderColor: lightMode ? '#e4e4e7' : '#3f3f46' }}>
      <span className={`text-[10px] uppercase tracking-wide ${lightMode ? 'text-zinc-400' : 'text-zinc-500'}`}>
        Huume · {steps.length} step{steps.length !== 1 ? 's' : ''}
      </span>
      <div className="flex flex-col gap-1">
        {steps.map((s) => {
          const Icon = s.status === 'error' ? XCircle : KIND_ICON[s.kind] ?? Bot
          return (
            <div
              key={s.seq}
              className={`flex items-start gap-1.5 text-[11px] rounded border px-1.5 py-1 ${statusColor(s.status, lightMode)}`}
            >
              <Icon size={12} className="shrink-0 mt-0.5" />
              <span className="flex-1 leading-tight">
                {s.label}
                {s.detail && <span className="opacity-70"> — {s.detail}</span>}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
