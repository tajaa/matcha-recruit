import { useEffect, useState } from 'react'
import { FileArchive, FileText, Loader2 } from 'lucide-react'
import { Button } from '../../../components/ui'
import type { EvidencePreview, Matter } from '../../../api/legalDefense'
import { LABEL, SOURCE_META, typeLabel } from './shared'

/** Docket header: matter caption + the systems strip (which internal systems
 *  feed this matter, live counts) + packet-generation state. */
export function Masthead({ matter, evidence, genKind, hasAssistant, onGenerate }: {
  matter: Matter
  evidence: EvidencePreview | null
  genKind: 'pdf' | 'zip' | 'both' | null
  hasAssistant: boolean
  onGenerate: (kind: 'pdf' | 'both') => void
}) {
  const window =
    matter.evidence_start || matter.evidence_end
      ? `${matter.evidence_start ?? '…'} → ${matter.evidence_end ?? '…'}`
      : 'All records'

  return (
    <div className="shrink-0 border-b border-white/[0.06]">
      <div className="flex items-start justify-between gap-4 px-5 pt-4">
        <div className="min-w-0">
          <div className={LABEL}>Matter</div>
          <h2 className="mt-0.5 truncate text-lg font-semibold tracking-tight text-zinc-100">{matter.title}</h2>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] uppercase tracking-wide text-zinc-500">
            <span>{typeLabel(matter.matter_type)}</span>
            <span className={matter.status === 'active' ? 'text-emerald-400' : 'text-zinc-500'}>{matter.status}</span>
            <span className="normal-case text-zinc-500">window {window}</span>
            {matter.counsel_directed && (
              <span className="text-zinc-400">at direction of counsel{matter.counsel_name ? ` · ${matter.counsel_name}` : ''}</span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2 pt-1">
          <Button size="sm" variant="secondary" disabled={!hasAssistant || genKind !== null} onClick={() => onGenerate('pdf')}>
            {genKind === 'pdf' ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />} Memo PDF
          </Button>
          <Button size="sm" variant="secondary" disabled={!hasAssistant || genKind !== null} onClick={() => onGenerate('both')}>
            {genKind === 'both' ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileArchive className="h-4 w-4" />} PDF + ZIP
          </Button>
        </div>
      </div>

      <SystemsStrip key={matter.id} evidence={evidence} />

      {genKind && (
        <div className="flex items-center gap-2 border-t border-emerald-500/20 bg-emerald-500/[0.04] px-5 py-1.5">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
          <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-emerald-300/90">
            Assembling packet — rendering memo + per-record case files
          </span>
        </div>
      )}
    </div>
  )
}

function SystemsStrip({ evidence }: { evidence: EvidencePreview | null }) {
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(id)
  }, [])

  return (
    <div className="mt-3 flex items-stretch divide-x divide-white/[0.06] overflow-x-auto border-t border-white/[0.06]">
      <div className="flex shrink-0 items-center gap-2.5 py-2.5 pl-5 pr-4">
        <span className={LABEL}>In scope</span>
        <span className="font-mono text-sm font-semibold tabular-nums text-emerald-400">
          {evidence ? evidence.total : '·'}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-wide text-zinc-600">records</span>
      </div>
      {SOURCE_META.map((s, i) => {
        const src = evidence?.sources[s.key]
        const active = !!src && src.records.length > 0
        const Icon = s.icon
        return (
          <div
            key={s.key}
            className={`flex shrink-0 items-center gap-2 px-4 py-2.5 transition-opacity duration-300 motion-reduce:transition-none ${shown ? 'opacity-100' : 'opacity-0'}`}
            style={{ transitionDelay: `${i * 40}ms` }}
            title={src ? src.label : `${s.label}: no records in the matter window`}
          >
            <Icon className={`h-3.5 w-3.5 ${active ? 'text-emerald-400' : 'text-zinc-700'}`} />
            <span className={`text-[10px] font-medium uppercase tracking-[0.15em] ${active ? 'text-zinc-300' : 'text-zinc-600'}`}>
              {s.label}
            </span>
            <span className={`font-mono text-xs tabular-nums ${active ? 'text-zinc-100' : 'text-zinc-700'}`}>
              {active ? src.records.length : '—'}
            </span>
          </div>
        )
      })}
    </div>
  )
}
