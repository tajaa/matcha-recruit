import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import type { EvidencePreview } from '../../../api/legalDefense'
import { LABEL, SOURCE_META } from './shared'

/** Evidence browser: every in-scope source expands to its record list —
 *  ref, one-line summary, date. Data is the already-fetched preview corpus. */
export function EvidencePanel({ evidence }: { evidence: EvidencePreview | null }) {
  const [open, setOpen] = useState<Record<string, boolean>>({})

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-baseline justify-between px-4 pb-2 pt-4">
        <span className={LABEL}>Evidence</span>
        <span className="font-mono text-[11px] tabular-nums text-zinc-500">
          {evidence ? `${evidence.total} records` : '…'}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {!evidence ? (
          <p className="px-4 py-2 text-xs text-zinc-600">Loading the record…</p>
        ) : evidence.total === 0 ? (
          <p className="px-4 py-2 text-xs text-zinc-500">
            No records fall inside the matter's evidence window. Widen the window when creating the matter to pull more history in.
          </p>
        ) : (
          <>
            {SOURCE_META.map((meta) => {
              const src = evidence.sources[meta.key]
              if (!src || src.records.length === 0) return null
              const isOpen = !!open[meta.key]
              const Icon = meta.icon
              return (
                <div key={meta.key} className="border-t border-white/[0.04] first:border-t-0">
                  <button
                    onClick={() => setOpen((o) => ({ ...o, [meta.key]: !o[meta.key] }))}
                    className="flex w-full items-center gap-2 px-4 py-2 text-left transition-colors hover:bg-white/[0.02]"
                  >
                    <ChevronRight className={`h-3 w-3 shrink-0 text-zinc-600 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                    <Icon className="h-3.5 w-3.5 shrink-0 text-emerald-400/80" />
                    <span className="flex-1 truncate text-xs text-zinc-300">{src.label}</span>
                    <span className="font-mono text-[11px] tabular-nums text-zinc-500">{src.records.length}</span>
                  </button>
                  {isOpen && (
                    <div className="border-t border-white/[0.04] bg-white/[0.01] pb-1">
                      {src.records.map((r) => (
                        <div key={r.cid} className="px-4 py-1.5 pl-9">
                          <div className="flex items-baseline justify-between gap-2 font-mono text-[10px] tabular-nums">
                            <span className="truncate text-zinc-400">{r.ref || '—'}</span>
                            <span className="shrink-0 text-zinc-600">{r.when || ''}</span>
                          </div>
                          <div className="truncate text-[11px] leading-snug text-zinc-500" title={r.summary}>
                            {r.summary}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
            {evidence.notes.length > 0 && (
              <div className="border-t border-white/[0.04] px-4 py-2">
                {evidence.notes.map((n, i) => (
                  <p key={i} className="text-[10px] leading-relaxed text-zinc-600">{n}</p>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
