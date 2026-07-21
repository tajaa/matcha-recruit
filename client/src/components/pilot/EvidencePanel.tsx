import { useState, type ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import { HelpHint } from '../ui/HelpHint'
import { LABEL } from '../ui'
import type { PilotSourceMeta } from './SystemsStrip'

/** The record shape both pilots' corpora expose (Broker `CorpusRecord`, Legal
 *  `EvidenceRecord` — both structurally this). */
export type PilotEvidenceRecord = { cid: string; ref: string | null; summary: string; when: string }

/** Evidence browser: an "Evidence · N records" header, loading/empty/populated
 *  branches, and a per-subsystem accordion (ChevronRight rotate + icon + label +
 *  count) whose expanded rows show ref / when / summary, closed by a notes
 *  footer. Shared by Broker Pilot and Legal Pilot.
 *
 *  Parameterized by `recordsFor` (each pilot buckets its own corpus), `labelFor`,
 *  the source-meta list, `total` (`null` = still loading), the empty-state copy,
 *  and the notes. `onRecordClick` is the one behavioural divergence: Legal rows
 *  are buttons opening a RecordViewer, so when it is supplied rows render as
 *  clickable (and truncated) buttons; Broker omits it and rows render as
 *  read-only divs. `footer` lets Legal mount its RecordViewer inside the panel
 *  exactly where it sat before; `className` carries Broker's extra `border-b`. */
export function EvidencePanel<SM extends PilotSourceMeta>({
  className,
  helpText,
  total,
  emptyText,
  sourceMeta,
  recordsFor,
  labelFor,
  notes,
  onRecordClick,
  footer,
}: {
  className?: string
  helpText: string
  total: number | null
  emptyText: string
  sourceMeta: readonly SM[]
  recordsFor: (key: string) => PilotEvidenceRecord[] | undefined
  labelFor: (meta: SM) => string
  notes: string[]
  onRecordClick?: (record: PilotEvidenceRecord, sourceLabel: string) => void
  footer?: ReactNode
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({})

  return (
    <div className={`flex flex-col${className ? ` ${className}` : ''}`}>
      <div className="flex items-baseline justify-between px-4 pb-2 pt-4">
        <span className="inline-flex items-center gap-1.5">
          <span className={LABEL}>Evidence</span>
          <HelpHint text={helpText} />
        </span>
        <span className="font-mono text-[11px] tabular-nums text-zinc-500">
          {total !== null ? `${total} records` : '…'}
        </span>
      </div>
      <div>
        {total === null ? (
          <p className="px-4 py-2 text-xs text-zinc-600">Loading the record…</p>
        ) : total === 0 ? (
          <p className="px-4 py-2 text-xs text-zinc-500">{emptyText}</p>
        ) : (
          <>
            {sourceMeta.map((meta) => {
              const records = recordsFor(meta.key)
              if (!records || records.length === 0) return null
              const isOpen = !!open[meta.key]
              const Icon = meta.icon
              const sourceLabel = labelFor(meta)
              return (
                <div key={meta.key} className="border-t border-white/[0.04] first:border-t-0">
                  <button
                    onClick={() => setOpen((o) => ({ ...o, [meta.key]: !o[meta.key] }))}
                    className="flex w-full items-center gap-2 px-4 py-2 text-left transition-colors hover:bg-white/[0.02]"
                  >
                    <ChevronRight className={`h-3 w-3 shrink-0 text-zinc-600 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                    <Icon className="h-3.5 w-3.5 shrink-0 text-emerald-400/80" />
                    <span className="flex-1 truncate text-xs text-zinc-300">{sourceLabel}</span>
                    <span className="font-mono text-[11px] tabular-nums text-zinc-500">{records.length}</span>
                  </button>
                  {isOpen && (
                    <div className="border-t border-white/[0.04] bg-white/[0.01] pb-1">
                      {records.map((r) => (
                        onRecordClick ? (
                          <button
                            key={r.cid}
                            onClick={() => onRecordClick(r, sourceLabel)}
                            className="block w-full px-4 py-1.5 pl-9 text-left transition-colors hover:bg-white/[0.03]"
                          >
                            <div className="flex items-baseline justify-between gap-2 font-mono text-[10px] tabular-nums">
                              <span className="truncate text-zinc-400">{r.ref || '—'}</span>
                              <span className="shrink-0 text-zinc-600">{r.when || ''}</span>
                            </div>
                            <div className="truncate text-[11px] leading-snug text-zinc-500" title={r.summary}>
                              {r.summary}
                            </div>
                          </button>
                        ) : (
                          <div key={r.cid} className="px-4 py-1.5 pl-9">
                            <div className="flex items-baseline justify-between gap-2 font-mono text-[10px] tabular-nums">
                              <span className="truncate text-zinc-400">{r.ref || '—'}</span>
                              <span className="shrink-0 text-zinc-600">{r.when || ''}</span>
                            </div>
                            <div className="text-[11px] leading-snug text-zinc-500" title={r.summary}>{r.summary}</div>
                          </div>
                        )
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
            {notes.length > 0 && (
              <div className="border-t border-white/[0.04] px-4 py-2">
                {notes.map((n, i) => (
                  <p key={i} className="text-[10px] leading-relaxed text-zinc-600">{n}</p>
                ))}
              </div>
            )}
          </>
        )}
      </div>
      {footer}
    </div>
  )
}
