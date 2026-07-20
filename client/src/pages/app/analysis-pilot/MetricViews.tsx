import { FileSpreadsheet, MessageSquarePlus } from 'lucide-react'
import { HelpHint } from '../../../components/ui/HelpHint'
import type { AnalysisDataset, MetricBlock } from '../../../api/analysis-pilot/analysisPilot'
import { slugify, type FocusChip } from './shared'

// --------------------------------------------------------------------------- //
// Metric block renderer (shared by dataset packs + comparisons).
// --------------------------------------------------------------------------- //

function Chart({ svg }: { svg: string }) {
  // Server-generated SVG, but its axis/series labels come from user-uploaded
  // datasets, and inline SVG is a scripting context (`<script>`, `onload=`).
  // Rendered as an <img> data-URI instead: identical pixels, but the SVG is a
  // passive image — browsers refuse to run script in one, so no escaping bug
  // upstream can become XSS here.
  // An <img> renders the SVG as its own isolated document, so it no longer
  // inherits the page font — and charts.py sets font-size but never
  // font-family, which would drop every axis label to the browser default
  // serif. Inject a font-family on the root <svg> to keep the rendering the
  // inline version had.
  const styled = svg.replace(
    /^\s*<svg\b/,
    '<svg font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"',
  )
  return (
    <div className="overflow-x-auto">
      <img src={`data:image/svg+xml;utf8,${encodeURIComponent(styled)}`} alt="" className="max-w-full" />
    </div>
  )
}

export function BlockView({ block, onFocus }: { block: MetricBlock; onFocus?: (chip: FocusChip) => void }) {
  return (
    <div className="mb-5">
      <div className="text-xs font-semibold uppercase tracking-wide text-emerald-400/90 mb-2">{block.label}</div>
      {block.tiles && block.tiles.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {block.tiles.map((t, i) => (
            <div key={i} className="flex-1 min-w-[120px] rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
              <div className="text-[10px] uppercase tracking-wide text-zinc-500">{t.label}</div>
              <div className="text-base font-semibold text-zinc-100 mt-0.5">{t.value}</div>
            </div>
          ))}
        </div>
      )}
      {block.charts?.map((c, i) => (
        <div key={i} className="mb-3">
          <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">{c.title}</div>
          <div className="rounded-lg border border-zinc-800 bg-white p-2 inline-block max-w-full">
            <Chart svg={c.svg} />
          </div>
        </div>
      ))}
      {block.tables?.map((tbl, i) => (
        <div key={i} className="mb-3">
          <div className="text-[11px] font-medium text-zinc-300 mb-1">{tbl.title}</div>
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-zinc-900/60">
                  {tbl.columns.map((c, j) => (
                    <th key={j} className="text-left px-2.5 py-1.5 text-[10px] uppercase tracking-wide text-zinc-500">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tbl.rows.map((row, r) => (
                  <tr key={r} className="border-t border-zinc-800/60">
                    {row.map((cell, c) => (
                      <td key={c} className={`px-2.5 py-1.5 ${c === 0 ? 'text-zinc-300' : 'text-zinc-400'}`}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
      {onFocus && (block.records?.length ?? 0) > 0 && (
        <details className="mt-1">
          <summary className="text-[11px] text-zinc-500 cursor-pointer hover:text-emerald-400">
            Citable records ({block.records!.length}) — click one to discuss it in chat
          </summary>
          <ul className="mt-1.5 space-y-1 max-h-48 overflow-y-auto pr-1">
            {block.records!.map((r) => (
              <li key={r.cid}>
                <button onClick={() => onFocus({ cid: r.cid, label: r.ref })}
                  className="w-full text-left text-[11px] text-zinc-400 hover:text-emerald-300 hover:bg-zinc-800/60 rounded px-1.5 py-1 inline-flex items-start gap-1.5">
                  <MessageSquarePlus className="h-3 w-3 mt-0.5 shrink-0 text-emerald-500/70" />
                  <span>{r.summary}</span>
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

export function MetricsTab({ datasets, onFocus }: { datasets: AnalysisDataset[]; onFocus?: (chip: FocusChip) => void }) {
  if (datasets.length === 0) {
    return <p className="text-sm text-zinc-600 p-6">Upload a dataset to see its computed metrics here.</p>
  }
  return (
    <div className="p-4">
      {datasets.map((d) => {
        const packs = Object.entries(d.metrics || {})
        return (
          <div key={d.id} className="mb-6">
            <div className="flex items-center gap-2 mb-2">
              <FileSpreadsheet className="h-4 w-4 text-zinc-500" />
              <span className="text-sm font-semibold text-zinc-200">{d.filename}</span>
              <span className="text-[10px] uppercase tracking-wide text-zinc-500">{d.normalized.kind}</span>
              {d.status === 'needs_review' && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400">figures pending review</span>
              )}
              <HelpHint text="Each bracketed id (metric:/ratio:/corr:) is a citable computed record — click one to focus your next chat question on it." />
            </div>
            {d.source_kind === 'pdf' && d.extraction && d.extraction.line_items.length > 0 && (
              <div className="mb-3">
                <div className="text-[11px] font-medium text-zinc-300 mb-1">Extracted figures — click a line to discuss it in chat</div>
                <ul className="space-y-0.5">
                  {d.extraction.line_items.map((it) => (
                    <li key={it.label}>
                      <button
                        onClick={() => onFocus?.({ cid: `figure:${d.id}:${slugify(it.label)}`, label: `${d.filename}: ${it.label}` })}
                        className="w-full text-left text-[11px] text-zinc-400 hover:text-emerald-300 hover:bg-zinc-800/60 rounded px-1.5 py-1 inline-flex items-center gap-1.5">
                        <MessageSquarePlus className="h-3 w-3 shrink-0 text-emerald-500/70" />
                        <span className="truncate">
                          {it.label}{it.page ? ` (p.${it.page})` : ''}: {it.values.map((v) => v ?? '—').join(', ')}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {packs.length === 0 && <p className="text-xs text-zinc-600">No metrics computed for this dataset.</p>}
            {packs.map(([k, block]) => <BlockView key={k} block={block} onFocus={onFocus} />)}
          </div>
        )
      })}
    </div>
  )
}
