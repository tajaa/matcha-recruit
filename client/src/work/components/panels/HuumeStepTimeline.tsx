import { useState } from 'react'
import { CheckCircle2, ChevronDown, ChevronRight, XCircle, Clock, FileSearch, Bot } from 'lucide-react'
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

function PayloadBlock({ label, value, lightMode }: { label: 'args' | 'result'; value: unknown; lightMode?: boolean }) {
  // JSON.stringify can throw on a circular ref (shouldn't occur — these
  // payloads are JSON-parsed off the SSE stream — but a metadata shape
  // change must never crash the message bubble).
  let text: string
  try {
    text = JSON.stringify(value, null, 2) ?? String(value)
  } catch {
    text = String(value)
  }
  return (
    <div>
      <span className="text-[9px] uppercase tracking-wide opacity-60">{label}</span>
      <pre className={`text-[10px] font-mono whitespace-pre-wrap break-all max-h-40 overflow-auto rounded p-1.5 mt-0.5 ${
        lightMode ? 'bg-zinc-100 text-zinc-700' : 'bg-zinc-900/70 text-zinc-300'
      }`}>{text}</pre>
    </div>
  )
}

/** Huume's per-turn tool-call timeline — rendered under an assistant bubble
 * from `message.metadata.huume_steps` (persisted so it survives reload,
 * matching how HR Pilot citations persist on message metadata), or live
 * from accumulated `step` SSE frames while a turn is streaming. Rows whose
 * step carries `args`/`result` (harness added this after the initial
 * timeline shipped) are expandable; rows without them — including every
 * message persisted before that change — render exactly as before. */
export default function HuumeStepTimeline({ steps, lightMode }: { steps: HuumeStep[]; lightMode?: boolean }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  if (!steps || steps.length === 0) return null

  function toggle(seq: number) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(seq)) next.delete(seq)
      else next.add(seq)
      return next
    })
  }

  return (
    <div className="mt-2.5 space-y-1 border-t pt-2" style={{ borderColor: lightMode ? '#e4e4e7' : '#3f3f46' }}>
      <span className={`text-[10px] uppercase tracking-wide ${lightMode ? 'text-zinc-400' : 'text-zinc-500'}`}>
        Huume · {steps.length} step{steps.length !== 1 ? 's' : ''}
      </span>
      <div className="flex flex-col gap-1">
        {steps.map((s) => {
          const Icon = s.status === 'error' ? XCircle : KIND_ICON[s.kind] ?? Bot
          const hasPayload = s.args != null || s.result != null
          const isOpen = expanded.has(s.seq)
          return (
            <div
              key={s.seq}
              className={`rounded border px-1.5 py-1 text-[11px] ${statusColor(s.status, lightMode)}`}
            >
              {hasPayload ? (
                <button
                  type="button"
                  onClick={() => toggle(s.seq)}
                  className="w-full flex items-start gap-1.5 text-left"
                >
                  <Icon size={12} className="shrink-0 mt-0.5" />
                  <span className="flex-1 leading-tight">
                    {s.label}
                    {s.detail && <span className="opacity-70"> — {s.detail}</span>}
                  </span>
                  {isOpen ? <ChevronDown size={12} className="shrink-0 mt-0.5 opacity-60" /> : <ChevronRight size={12} className="shrink-0 mt-0.5 opacity-60" />}
                </button>
              ) : (
                <div className="flex items-start gap-1.5">
                  <Icon size={12} className="shrink-0 mt-0.5" />
                  <span className="flex-1 leading-tight">
                    {s.label}
                    {s.detail && <span className="opacity-70"> — {s.detail}</span>}
                  </span>
                </div>
              )}
              {hasPayload && isOpen && (
                <div className="mt-1.5 flex flex-col gap-1.5">
                  {s.args != null && <PayloadBlock label="args" value={s.args} lightMode={lightMode} />}
                  {s.result != null && <PayloadBlock label="result" value={s.result} lightMode={lightMode} />}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
