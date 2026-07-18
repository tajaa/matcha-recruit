import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import type { ContextPreview } from '../../../api/broker/brokerPilot'
import { HelpHint } from '../../../components/broker/HelpHint'
import { LABEL, SOURCE_META, SYSTEM_LABEL, deriveSystems } from './shared'

/** Evidence browser: every grounding subsystem expands to its records — ref,
 *  one-line summary, date. Data is the already-fetched context corpus, split
 *  into per-subsystem buckets. Read-only (platform records, not documents). */
export function EvidencePanel({ context }: { context: ContextPreview | null }) {
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const systems = deriveSystems(context)

  return (
    <div className="flex flex-col border-b border-white/[0.06]">
      <div className="flex items-baseline justify-between px-4 pb-2 pt-4">
        <span className="inline-flex items-center gap-1.5">
          <span className={LABEL}>Evidence</span>
          <HelpHint text="Every record the analyst can cite, grouped by system. Expand a system to browse its records — the same refs appear as citations under each answer, so you can trace any claim back to its source." />
        </span>
        <span className="font-mono text-[11px] tabular-nums text-zinc-500">
          {context ? `${context.total} records` : '…'}
        </span>
      </div>
      <div>
        {!context ? (
          <p className="px-4 py-2 text-xs text-zinc-600">Loading the record…</p>
        ) : context.total === 0 ? (
          <p className="px-4 py-2 text-xs text-zinc-500">
            No platform data on file for this client yet. Upload documents, or add loss runs / EPL /
            property from the client's detail page to ground the analysis.
          </p>
        ) : (
          <>
            {SOURCE_META.map((meta) => {
              const records = systems[meta.key]
              if (!records || records.length === 0) return null
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
                    <span className="flex-1 truncate text-xs text-zinc-300">{SYSTEM_LABEL[meta.key] ?? meta.label}</span>
                    <span className="font-mono text-[11px] tabular-nums text-zinc-500">{records.length}</span>
                  </button>
                  {isOpen && (
                    <div className="border-t border-white/[0.04] bg-white/[0.01] pb-1">
                      {records.map((r) => (
                        <div key={r.cid} className="px-4 py-1.5 pl-9">
                          <div className="flex items-baseline justify-between gap-2 font-mono text-[10px] tabular-nums">
                            <span className="truncate text-zinc-400">{r.ref || '—'}</span>
                            <span className="shrink-0 text-zinc-600">{r.when || ''}</span>
                          </div>
                          <div className="text-[11px] leading-snug text-zinc-500" title={r.summary}>{r.summary}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
            {context.notes.length > 0 && (
              <div className="border-t border-white/[0.04] px-4 py-2">
                {context.notes.map((n, i) => (
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
