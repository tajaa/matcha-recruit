import { useMemo, useState } from 'react'
import { CalendarDays } from 'lucide-react'
import { HelpHint } from '../../../components/ui/HelpHint'
import type { EvidencePreview } from '../../../api/hr/legalDefense'
import { LABEL } from './shared'
import { RecordViewer, type ViewerTarget } from './RecordViewer'

/** Merged timeline of every dated company record in the evidence scope,
 *  oldest first — the attorney's chronology, assembled from data the corpus
 *  already carries (when_iso). Mirrors the PDF's "Chronology of records"
 *  section (legal_defense._chronology_rows): company-conduct events only —
 *  compliance posture (`compliance`) and jurisdiction context are excluded. */

const EXCLUDED_SOURCES = new Set(['compliance', 'law', 'legislation', 'case_law'])

type Row = {
  cid: string
  ref: string | null
  summary: string
  when: string
  when_iso: string | null
  sourceLabel: string
}

function monthLabel(ym: string): string {
  const d = new Date(`${ym}-01T00:00:00`)
  return isNaN(d.getTime()) ? ym : d.toLocaleDateString([], { month: 'long', year: 'numeric' })
}

export function Chronology({ evidence }: { evidence: EvidencePreview | null }) {
  const [view, setView] = useState<ViewerTarget | null>(null)

  const groups = useMemo(() => {
    if (!evidence) return []
    const rows: Row[] = []
    for (const [key, s] of Object.entries(evidence.sources)) {
      if (EXCLUDED_SOURCES.has(key)) continue
      for (const r of s.records) {
        rows.push({
          cid: r.cid, ref: r.ref, summary: r.summary, when: r.when,
          when_iso: r.when_iso ?? null, sourceLabel: s.label,
        })
      }
    }
    const dated = rows
      .filter((r) => r.when_iso)
      .sort((a, b) => a.when_iso!.localeCompare(b.when_iso!))
    const undated = rows.filter((r) => !r.when_iso)

    const out: { label: string; rows: Row[] }[] = []
    for (const r of dated) {
      const label = monthLabel(r.when_iso!.slice(0, 7))
      const last = out[out.length - 1]
      if (last && last.label === label) last.rows.push(r)
      else out.push({ label, rows: [r] })
    }
    if (undated.length > 0) out.push({ label: 'Undated', rows: undated })
    return out
  }, [evidence])

  if (!evidence) {
    return <p className="px-5 py-8 text-sm text-zinc-500">Assembling the record…</p>
  }

  if (groups.length === 0) {
    return (
      <div className="px-5 py-8">
        <div className={LABEL}>Chronology</div>
        <p className="mt-2 max-w-[60ch] text-sm leading-relaxed text-zinc-400">
          No dated company records in the evidence scope. Widen the matter's window
          or clear its location scope to see more.
        </p>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-5 py-4">
        <div className="flex items-center gap-2">
          <CalendarDays className="h-3.5 w-3.5 text-emerald-400/80" />
          <span className={LABEL}>Chronology — oldest first</span>
          <HelpHint text="Every dated record across your systems, merged into one timeline. It mirrors the chronology section in the exported memo." />
        </div>
        {groups.map((g) => (
          <div key={g.label} className="mt-5">
            <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-500">{g.label}</div>
            <div className="mt-1.5">
              {g.rows.map((r) => (
                <button
                  key={r.cid}
                  onClick={() => setView({ cid: r.cid, ref: r.ref, sourceLabel: r.sourceLabel, summary: r.summary, when: r.when })}
                  className="group flex w-full items-start gap-3 border-t border-white/[0.06] py-2 text-left last:border-b last:border-white/[0.06] hover:bg-white/[0.02]"
                >
                  <span className="w-20 shrink-0 pt-px font-mono text-[10px] tabular-nums text-zinc-500">
                    {r.when_iso ? r.when_iso.slice(0, 10) : '—'}
                  </span>
                  <span className="w-32 shrink-0 truncate pt-px text-[10px] font-medium uppercase tracking-wide text-zinc-500">
                    {r.sourceLabel}
                  </span>
                  <span className="min-w-0 flex-1 text-[13px] leading-snug text-zinc-300 transition-colors group-hover:text-zinc-100">
                    {r.summary}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {view && <RecordViewer target={view} onClose={() => setView(null)} />}
    </div>
  )
}
