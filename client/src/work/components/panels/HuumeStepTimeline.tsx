import { useState } from 'react'
import { CheckCircle2, ChevronDown, ChevronRight, XCircle, Clock, FileSearch, Bot } from 'lucide-react'
import type { HuumeStep } from '../../types'

const KIND_ICON: Record<HuumeStep['kind'], typeof FileSearch> = {
  read: FileSearch,
  staged: Clock,
  write: Bot,
  finish: CheckCircle2,
}

// Status only tints the row's icon now (see the collapse rewrite below) — no
// per-row filled/bordered box, so this only needs a text color per status.
function statusIconColor(status: HuumeStep['status']) {
  switch (status) {
    case 'ok': return 'text-emerald-500'
    case 'rejected': return 'text-amber-500'
    case 'error': return 'text-red-500'
    default: return 'text-w-faint'
  }
}

function PayloadBlock({ label, value }: { label: 'args' | 'result'; value: unknown }) {
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
      <pre className="text-[10px] font-mono whitespace-pre-wrap break-all max-h-40 overflow-auto rounded p-1.5 mt-0.5 bg-w-surface2 text-w-text">{text}</pre>
    </div>
  )
}

/** Huume's per-turn tool-call timeline — rendered under an assistant bubble
 * from `message.metadata.huume_steps` (persisted so it survives reload,
 * matching how HR Pilot citations persist on message metadata), or live
 * from accumulated `step` SSE frames while a turn is streaming (`live`).
 *
 * Collapsed by default — a persisted timeline shows one quiet "N steps" row;
 * a live one shows the latest step's label with a pulse, so a long tool
 * chain doesn't grow a wall of colored boxes under every turn. Click to
 * expand either way; rows whose step carries `args`/`result` (harness added
 * this after the initial timeline shipped) are further expandable for the
 * raw payload — rows without them render as plain text, including every
 * message persisted before that change. */
export default function HuumeStepTimeline({ steps, live }: { steps: HuumeStep[]; lightMode?: boolean; live?: boolean }) {
  const [open, setOpen] = useState(false)
  const [expandedPayloads, setExpandedPayloads] = useState<Set<number>>(new Set())

  if (!steps || steps.length === 0) return null

  function togglePayload(seq: number) {
    setExpandedPayloads((prev) => {
      const next = new Set(prev)
      if (next.has(seq)) next.delete(seq)
      else next.add(seq)
      return next
    })
  }

  if (!open) {
    const latest = steps[steps.length - 1]
    return (
      <div className="mt-2 pt-2 border-t border-w-line">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="w-full flex items-center gap-1.5 text-[11px] text-w-dim hover:text-w-text transition-colors"
        >
          <Bot size={12} className={`shrink-0 ${live ? 'animate-pulse' : ''}`} />
          <span className="flex-1 text-left truncate">
            {live
              ? `Step ${steps.length} · ${latest.label}${latest.detail ? ` — ${latest.detail}` : ''}`
              : `${steps.length} step${steps.length !== 1 ? 's' : ''}`}
          </span>
          <ChevronRight size={12} className="shrink-0 opacity-60" />
        </button>
      </div>
    )
  }

  return (
    <div className="mt-2 pt-2 border-t border-w-line">
      <button
        type="button"
        onClick={() => setOpen(false)}
        className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-w-faint mb-1 hover:text-w-dim transition-colors"
      >
        <ChevronDown size={11} />
        Huume · {steps.length} step{steps.length !== 1 ? 's' : ''}
      </button>
      <div className="flex flex-col gap-1 border-l border-w-line pl-2">
        {steps.map((s) => {
          const Icon = s.status === 'error' ? XCircle : KIND_ICON[s.kind] ?? Bot
          const hasPayload = s.args != null || s.result != null
          const isPayloadOpen = expandedPayloads.has(s.seq)
          return (
            <div key={s.seq} className="text-[11px] text-w-dim">
              {hasPayload ? (
                <button
                  type="button"
                  onClick={() => togglePayload(s.seq)}
                  className="w-full flex items-start gap-1.5 text-left hover:text-w-text transition-colors"
                >
                  <Icon size={12} className={`shrink-0 mt-0.5 ${statusIconColor(s.status)}`} />
                  <span className="flex-1 leading-tight">
                    {s.label}
                    {s.detail && <span className="opacity-70"> — {s.detail}</span>}
                  </span>
                  {isPayloadOpen ? <ChevronDown size={12} className="shrink-0 mt-0.5 opacity-60" /> : <ChevronRight size={12} className="shrink-0 mt-0.5 opacity-60" />}
                </button>
              ) : (
                <div className="flex items-start gap-1.5">
                  <Icon size={12} className={`shrink-0 mt-0.5 ${statusIconColor(s.status)}`} />
                  <span className="flex-1 leading-tight">
                    {s.label}
                    {s.detail && <span className="opacity-70"> — {s.detail}</span>}
                  </span>
                </div>
              )}
              {hasPayload && isPayloadOpen && (
                <div className="mt-1.5 ml-[18px] flex flex-col gap-1.5">
                  {s.args != null && <PayloadBlock label="args" value={s.args} />}
                  {s.result != null && <PayloadBlock label="result" value={s.result} />}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
