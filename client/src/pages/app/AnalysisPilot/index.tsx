import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Activity, BarChart3, Check, Download, FileSpreadsheet, FileText, GitCompare, Loader2,
  MessageSquarePlus, Plus, RefreshCw, Send, Sparkles, Trash2, Wand2, X,
} from 'lucide-react'
import { FileUpload } from '../../../components/ui/FileUpload'
import {
  listAnalysisSessions, getAnalysisSession, createAnalysisSession, uploadDataset, patchDataset,
  deleteDataset, createComparison, generateReport, downloadPacket, streamChat,
  type AnalysisSession, type AnalysisDataset, type AnalysisMessage, type MetricBlock,
  type Extraction, type ProposedEdit,
} from '../../../api/analysisPilot'

// ---------------------------------------------------------------------------
// Analysis Pilot — general-purpose bring-your-own-data analysis in a chat UI.
// Upload any dataset (CSV/XLSX/financial-document PDF); a deterministic engine
// computes the metrics (descriptive stats, volatility & risk, financial ratios,
// insurance, inventory); a grounded AI answers questions over the computed
// numbers and exports a report. Highlight a record to focus the chat on it —
// the AI can propose corrections to document-extracted figures, which apply
// only through the confirmed review PATCH. Numbers are computed in Python —
// the AI can only cite, never invent.
// ---------------------------------------------------------------------------

// A highlighted record attached to the next chat turn.
type FocusChip = { cid: string; label: string }

// Mirror of the server's analysis_packs.base.slug() — needed only to mint
// `figure:` cids for extraction rows (metric records carry their cid already).
const slugify = (s: string) =>
  s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'x'

// Fallback only — the authoritative role vocabulary is served by the backend
// on the session payload (`canonical_roles`), so new analyzer packs' roles
// appear here without a frontend change.
const ROLE_OPTIONS_FALLBACK = [
  'revenue', 'cogs', 'gross_profit', 'operating_income', 'net_income',
  'interest_expense', 'total_assets', 'current_assets', 'cash', 'receivables',
  'inventory_value', 'current_liabilities', 'total_liabilities', 'total_equity',
  'premium', 'exposure', 'losses_incurred', 'losses_paid', 'reserves',
  'claim_count', 'open_claims', 'units_on_hand', 'units_sold', 'reorder_point',
  'lead_time', 'return', 'price', 'score',
]

export default function AnalysisPilot() {
  const [sessions, setSessions] = useState<AnalysisSession[]>([])
  const [active, setActive] = useState<AnalysisSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const activeIdRef = useRef<string | null>(null)

  const refreshList = useCallback(async () => {
    const rows = await listAnalysisSessions()
    setSessions(rows)
    return rows
  }, [])

  const openSession = useCallback(async (id: string) => {
    activeIdRef.current = id
    try {
      const full = await getAnalysisSession(id)
      if (activeIdRef.current === id) setActive(full)
    } catch {
      if (activeIdRef.current === id) setActive(null)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const rows = await refreshList()
        if (!cancelled && rows.length) void openSession(rows[0].id)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const reloadActive = useCallback(async () => {
    const id = activeIdRef.current
    if (!id) return
    try {
      const full = await getAnalysisSession(id)
      if (activeIdRef.current === id) setActive(full)
    } catch { /* keep current */ }
    void refreshList()
  }, [refreshList])

  const onCreated = useCallback(async (s: AnalysisSession) => {
    setShowNew(false)
    await refreshList()
    void openSession(s.id)
  }, [refreshList, openSession])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-72">
        <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-4">
      <aside className="w-60 shrink-0 flex flex-col border border-zinc-800 rounded-xl bg-zinc-950/40">
        <div className="p-3 border-b border-zinc-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-emerald-500" />
            <span className="text-sm font-semibold text-zinc-200">Analysis Pilot</span>
          </div>
          <button onClick={() => setShowNew(true)} title="New session"
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-emerald-400">
            <Plus className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.length === 0 && (
            <p className="text-xs text-zinc-600 p-3">No analyses yet. Upload any data — financials, loss runs, prices, scores — and ask questions about it.</p>
          )}
          {sessions.map((s) => (
            <button key={s.id} onClick={() => openSession(s.id)}
              className={`w-full text-left px-3 py-2 rounded-lg transition ${
                active?.id === s.id ? 'bg-emerald-500/10 border border-emerald-500/30' : 'hover:bg-zinc-800/60 border border-transparent'
              }`}>
              <div className="text-sm text-zinc-200 truncate">{s.title}</div>
              <div className="text-[11px] text-zinc-500 flex gap-2 mt-0.5">
                <span>{s.dataset_count ?? 0} datasets</span>
                {(s.packet_count ?? 0) > 0 && <span className="text-emerald-500">{s.packet_count} reports</span>}
              </div>
            </button>
          ))}
        </div>
      </aside>

      <main className="flex-1 min-w-0">
        {active ? (
          <Workbench key={active.id} session={active} onChange={reloadActive} />
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-center">
            <Wand2 className="h-8 w-8 text-emerald-500 mb-3" />
            <h2 className="text-lg font-semibold text-zinc-100">Analyze any data in a grounded chat</h2>
            <p className="text-sm text-zinc-500 mt-2 max-w-md">
              Upload a CSV, spreadsheet, or a financial document — a P&L, a loss run, prices, scores,
              inventory. The engine computes the metrics (trends, ratios, volatility & risk); the pilot
              answers your questions citing only those computed numbers.
            </p>
            <button onClick={() => setShowNew(true)}
              className="mt-5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium inline-flex items-center gap-2">
              <Plus className="h-4 w-4" /> New analysis
            </button>
          </div>
        )}
      </main>

      {showNew && <NewSessionModal onClose={() => setShowNew(false)} onCreated={onCreated} />}
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Workbench — datasets rail + tabbed (metrics / chat / compare) center.
// --------------------------------------------------------------------------- //

type Tab = 'metrics' | 'chat' | 'compare'

function Workbench({ session, onChange }: { session: AnalysisSession; onChange: () => void }) {
  const [tab, setTab] = useState<Tab>('metrics')
  const [reporting, setReporting] = useState(false)
  // Highlighted records for the next chat turn — adding one jumps to the chat.
  const [focus, setFocus] = useState<FocusChip[]>([])
  const addFocus = useCallback((chip: FocusChip) => {
    setFocus((f) => (f.some((c) => c.cid === chip.cid) || f.length >= 10 ? f : [...f, chip]))
    setTab('chat')
  }, [])
  const removeFocus = useCallback((cid: string) => setFocus((f) => f.filter((c) => c.cid !== cid)), [])
  const clearFocus = useCallback(() => setFocus([]), [])
  const datasets = session.datasets ?? []
  const ready = datasets.filter((d) => d.status === 'ready' || d.status === 'needs_review')

  const genReport = async () => {
    setReporting(true)
    try {
      const pkt = await generateReport(session.id)
      await downloadPacket(session.id, pkt)
      onChange()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Report generation failed.')
    } finally {
      setReporting(false)
    }
  }

  return (
    <div className="h-full flex gap-4">
      <div className="w-72 shrink-0 overflow-y-auto">
        <DatasetsPanel session={session} onChange={onChange} onFocus={addFocus} />
      </div>
      <div className="flex-1 min-w-0 flex flex-col border border-zinc-800 rounded-xl bg-zinc-950/40">
        <div className="px-4 py-2.5 border-b border-zinc-800 flex items-center justify-between">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-zinc-100 truncate">{session.title}</div>
            {session.goal && <div className="text-xs text-zinc-500 truncate">{session.goal}</div>}
          </div>
          <button onClick={() => void genReport()} disabled={reporting || ready.length === 0}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white inline-flex items-center gap-1.5 shrink-0">
            {reporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
            Report
          </button>
        </div>
        <div className="px-3 pt-2 flex gap-1 border-b border-zinc-800">
          {(['metrics', 'chat', 'compare'] as Tab[]).map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-3 py-1.5 text-xs rounded-t-lg capitalize ${
                tab === t ? 'bg-zinc-800 text-emerald-400' : 'text-zinc-500 hover:text-zinc-300'
              }`}>
              {t === 'metrics' ? 'Metrics' : t === 'chat' ? 'Analyst Chat' : 'Compare'}
            </button>
          ))}
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto">
          {tab === 'metrics' && <MetricsTab datasets={ready} onFocus={addFocus} />}
          {tab === 'chat' && (
            <Console session={session} onTurn={onChange} focus={focus}
              onRemoveFocus={removeFocus} onClearFocus={clearFocus} />
          )}
          {tab === 'compare' && <CompareTab session={session} onChange={onChange} />}
        </div>
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Metric block renderer (shared by dataset packs + comparisons).
// --------------------------------------------------------------------------- //

function Chart({ svg }: { svg: string }) {
  // Server-generated, escaped inline SVG from our own backend.
  return <div className="overflow-x-auto" dangerouslySetInnerHTML={{ __html: svg }} />
}

function BlockView({ block, onFocus }: { block: MetricBlock; onFocus?: (chip: FocusChip) => void }) {
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

function MetricsTab({ datasets, onFocus }: { datasets: AnalysisDataset[]; onFocus?: (chip: FocusChip) => void }) {
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

// --------------------------------------------------------------------------- //
// Datasets panel — upload + list + review/mapping + delete.
// --------------------------------------------------------------------------- //

function DatasetsPanel({ session, onChange, onFocus }: {
  session: AnalysisSession; onChange: () => void; onFocus?: (chip: FocusChip) => void
}) {
  const [busy, setBusy] = useState(false)
  const [retrying, setRetrying] = useState<string | null>(null)
  // Store only the id — the modal derives the dataset from the refreshed
  // session, so a mid-review refresh can't resurrect a stale snapshot.
  const [reviewId, setReviewId] = useState<string | null>(null)
  const datasets = session.datasets ?? []
  const review = reviewId ? datasets.find((d) => d.id === reviewId) ?? null : null

  // Dataset deleted (or session reloaded without it) while the modal was open.
  useEffect(() => {
    if (reviewId && !datasets.some((d) => d.id === reviewId)) setReviewId(null)
  }, [reviewId, datasets])

  const onFiles = async (files: File[]) => {
    if (files.length === 0) return
    setBusy(true)
    try {
      for (const f of files) {
        await uploadDataset(session.id, f)
      }
      onChange()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Upload failed.')
    } finally {
      setBusy(false)
    }
  }

  const retryExtraction = async (id: string) => {
    setRetrying(id)
    try {
      await patchDataset(session.id, id, { reextract: true })
      onChange()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Re-extraction failed.')
    } finally {
      setRetrying(null)
    }
  }

  return (
    <div className="border border-zinc-800 rounded-xl bg-zinc-950/40">
      <div className="px-3 py-2.5 border-b border-zinc-800 flex items-center justify-between">
        <span className="text-sm font-semibold text-zinc-200">Datasets</span>
        {busy && <Loader2 className="h-3.5 w-3.5 animate-spin text-emerald-500" />}
      </div>
      <div className="p-2">
        <FileUpload onFiles={(files) => void onFiles(files)} accept=".csv,.xlsx,.pdf"
          multiple maxSizeMB={25} disabled={busy}>
          <p className="text-xs">Drop CSV, XLSX, or a financial PDF here, or <span className="underline">browse</span></p>
        </FileUpload>
      </div>
      <div className="p-2 pt-0 space-y-1.5 max-h-[62vh] overflow-y-auto">
        {datasets.length === 0 && (
          <p className="text-xs text-zinc-600 p-2">Upload CSV, XLSX, or a financial PDF (10-K, P&L, loss run).</p>
        )}
        {datasets.map((d) => (
          <div key={d.id} className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-2.5 py-2">
            <div className="flex items-center gap-2">
              {d.source_kind === 'pdf' ? <FileText className="h-3.5 w-3.5 text-zinc-500" /> : <FileSpreadsheet className="h-3.5 w-3.5 text-zinc-500" />}
              <span className="text-xs text-zinc-200 truncate flex-1">{d.filename}</span>
              <button onClick={() => void deleteDataset(session.id, d.id).then(onChange)}
                className="text-zinc-600 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
            </div>
            <div className="flex items-center gap-2 mt-1">
              <StatusPill status={d.status} />
              {(d.column_count ?? 0) > 0 && (
                <span className="text-[10px] text-zinc-600">{d.column_count} series · {d.row_count} rows</span>
              )}
              {d.status === 'failed' && d.source_kind === 'pdf' && (
                <button onClick={() => void retryExtraction(d.id)} disabled={retrying === d.id}
                  className="text-[10px] text-emerald-400 hover:underline ml-auto inline-flex items-center gap-1 disabled:opacity-40">
                  {retrying === d.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                  Retry extraction
                </button>
              )}
              {d.status !== 'processing' && d.status !== 'failed' && (
                <button onClick={() => setReviewId(d.id)}
                  className="text-[10px] text-emerald-400 hover:underline ml-auto">Review</button>
              )}
            </div>
            {d.error && <div className="text-[10px] text-amber-400 mt-1">{d.error}</div>}
            {(d.warnings ?? []).map((w, i) => (
              <div key={i} className="text-[10px] text-amber-400/70 mt-0.5">{w}</div>
            ))}
          </div>
        ))}
      </div>
      {review && (
        <MappingModal session={session} dataset={review}
          onClose={() => setReviewId(null)}
          onSaved={() => { setReviewId(null); onChange() }}
          onFocus={onFocus ? (chip) => { setReviewId(null); onFocus(chip) } : undefined} />
      )}
    </div>
  )
}

function StatusPill({ status }: { status: AnalysisDataset['status'] }) {
  const map: Record<AnalysisDataset['status'], string> = {
    processing: 'bg-zinc-700/40 text-zinc-400',
    ready: 'bg-emerald-500/15 text-emerald-400',
    needs_review: 'bg-amber-500/15 text-amber-400',
    failed: 'bg-red-500/15 text-red-400',
  }
  const label = status === 'needs_review' ? 'review' : status
  return <span className={`text-[10px] px-1.5 py-0.5 rounded ${map[status]}`}>{label}</span>
}

// --------------------------------------------------------------------------- //
// Mapping/review modal — confirm roles + config (+ document figures).
// --------------------------------------------------------------------------- //

function MappingModal({ session, dataset, onClose, onSaved, onFocus }: {
  session: AnalysisSession; dataset: AnalysisDataset; onClose: () => void; onSaved: () => void
  onFocus?: (chip: FocusChip) => void
}) {
  const roleOptions = ['', ...(session.canonical_roles ?? ROLE_OPTIONS_FALLBACK)]
  const [roles, setRoles] = useState<Record<string, string>>(() => ({ ...dataset.normalized.roles }))
  const [ppy, setPpy] = useState<string>(() => String((dataset.config?.periods_per_year as number) ?? ''))
  const [orientation, setOrientation] = useState<'' | 'columns' | 'rows'>('')
  const [busy, setBusy] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [extraction, setExtraction] = useState<Extraction | null>(dataset.extraction)
  const columns = dataset.normalized.columns
  const isTabular = dataset.source_kind !== 'pdf'

  const setFigure = (row: number, col: number, v: string) => {
    setExtraction((ex) => {
      if (!ex) return ex
      const items = ex.line_items.map((it, i) =>
        i === row ? { ...it, values: it.values.map((vv, j) => (j === col ? (v === '' ? null : Number(v)) : vv)) } : it)
      return { ...ex, line_items: items }
    })
  }

  const save = async () => {
    setBusy(true)
    setSaveError(null)
    try {
      await patchDataset(session.id, dataset.id, {
        mapping: roles,
        periods_per_year: ppy ? Number(ppy) : undefined,
        extraction: dataset.source_kind === 'pdf' && extraction ? extraction : undefined,
        orientation: isTabular && orientation ? orientation : undefined,
      })
      onSaved()
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Could not save.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-950 p-5"
        onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-semibold text-zinc-100 mb-1">Review — {dataset.filename}</h3>
        <p className="text-xs text-zinc-500 mb-4">
          Map each series to what it represents so the right metrics compute. Numbers are computed
          from these values — nothing is invented.
        </p>

        {dataset.source_kind === 'pdf' && extraction && extraction.line_items.length > 0 && (
          <div className="mb-4">
            <div className="text-xs font-medium text-zinc-300 mb-1">Extracted figures — verify before analyzing</div>
            <div className="overflow-x-auto rounded-lg border border-zinc-800">
              <table className="text-xs">
                <thead>
                  <tr className="bg-zinc-900/60">
                    <th className="px-2 py-1.5 text-left text-[10px] uppercase text-zinc-500">Line item</th>
                    {extraction.periods.map((p, i) => (
                      <th key={i} className="px-2 py-1.5 text-left text-[10px] uppercase text-zinc-500">{p}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {extraction.line_items.map((it, r) => (
                    <tr key={r} className="border-t border-zinc-800/60">
                      <td className="px-2 py-1 text-zinc-300 whitespace-nowrap">
                        {it.label}{it.page ? <span className="text-zinc-600"> · p.{it.page}</span> : null}
                        {onFocus && (
                          <button title="Discuss this figure in chat"
                            onClick={() => onFocus({ cid: `figure:${dataset.id}:${slugify(it.label)}`, label: `${dataset.filename}: ${it.label}` })}
                            className="ml-1.5 align-middle text-zinc-600 hover:text-emerald-400">
                            <MessageSquarePlus className="h-3 w-3" />
                          </button>
                        )}
                      </td>
                      {extraction.periods.map((_p, c) => (
                        <td key={c} className="px-1 py-1">
                          <input value={it.values[c] ?? ''} onChange={(e) => setFigure(r, c, e.target.value)}
                            className="w-20 rounded bg-zinc-900 border border-zinc-700 px-1.5 py-0.5 text-xs text-zinc-200" />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="text-xs font-medium text-zinc-300 mb-1">Series roles</div>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {columns.map((col) => (
            <div key={col} className="flex items-center gap-2">
              <span className="text-xs text-zinc-400 truncate flex-1" title={col}>{col}</span>
              <select value={roles[col] ?? ''} onChange={(e) => setRoles((r) => ({ ...r, [col]: e.target.value }))}
                className="rounded bg-zinc-900 border border-zinc-700 px-1.5 py-1 text-xs text-zinc-200 w-40">
                {roleOptions.map((o) => <option key={o} value={o}>{o || '(unmapped)'}</option>)}
              </select>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mb-5">
          <div className="flex items-center gap-2">
            <label className="text-xs text-zinc-400">Periods per year (for annualized vol)</label>
            <input value={ppy} onChange={(e) => setPpy(e.target.value.replace(/[^0-9]/g, ''))}
              placeholder="e.g. 252, 12" className="w-24 rounded bg-zinc-900 border border-zinc-700 px-2 py-1 text-xs text-zinc-200" />
          </div>
          {isTabular && (
            <div className="flex items-center gap-2">
              <label className="text-xs text-zinc-400" title="If the table was read the wrong way around, force how series are taken. Re-parses the original file.">
                Layout
              </label>
              <select value={orientation} onChange={(e) => setOrientation(e.target.value as '' | 'columns' | 'rows')}
                className="rounded bg-zinc-900 border border-zinc-700 px-1.5 py-1 text-xs text-zinc-200">
                <option value="">Auto-detected</option>
                <option value="columns">Columns are series</option>
                <option value="rows">Rows are series (line-items)</option>
              </select>
            </div>
          )}
        </div>

        {saveError && <div className="text-xs text-amber-400 mb-3">⚠ {saveError}</div>}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-2 text-sm text-zinc-400 hover:text-zinc-200">Cancel</button>
          <button onClick={() => void save()} disabled={busy}
            className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-medium inline-flex items-center gap-2">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Confirm & analyze
          </button>
        </div>
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Compare tab — build + view saved cross-dataset comparisons.
// --------------------------------------------------------------------------- //

function CompareTab({ session, onChange }: { session: AnalysisSession; onChange: () => void }) {
  const ready = (session.datasets ?? []).filter((d) => d.status === 'ready' || d.status === 'needs_review')
  const [selected, setSelected] = useState<string[]>([])
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const comparisons = session.comparisons ?? []

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  const build = async () => {
    if (selected.length < 2) return
    setBusy(true)
    try {
      await createComparison(session.id, { title: title.trim() || 'Comparison', dataset_ids: selected })
      setSelected([]); setTitle('')
      onChange()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Comparison failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="p-4">
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 mb-5">
        <div className="text-xs font-medium text-zinc-300 mb-2">Compare datasets (select 2+ in order)</div>
        <div className="space-y-1 mb-3">
          {ready.map((d) => (
            <label key={d.id} className="flex items-center gap-2 text-xs text-zinc-300">
              <input type="checkbox" checked={selected.includes(d.id)} onChange={() => toggle(d.id)} className="accent-emerald-500" />
              {d.filename}{selected.includes(d.id) && <span className="text-emerald-500">#{selected.indexOf(d.id) + 1}</span>}
            </label>
          ))}
          {ready.length < 2 && <p className="text-[11px] text-zinc-600">Add at least two analyzed datasets to compare.</p>}
        </div>
        <div className="flex gap-2">
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Comparison title (e.g. FY22 vs FY23)"
            className="flex-1 rounded bg-zinc-900 border border-zinc-700 px-2.5 py-1.5 text-xs text-zinc-200" />
          <button onClick={() => void build()} disabled={selected.length < 2 || busy}
            className="text-xs px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white inline-flex items-center gap-1.5">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <GitCompare className="h-3.5 w-3.5" />} Compare
          </button>
        </div>
      </div>
      {comparisons.map((c) => (
        <div key={c.id} className="mb-6">
          <div className="text-sm font-semibold text-zinc-200 mb-2 flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-zinc-500" /> {c.title}
          </div>
          <BlockView block={c.result} />
          {c.result.notes?.map((n, i) => <p key={i} className="text-[11px] text-amber-400/70">{n}</p>)}
        </div>
      ))}
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Console — grounded chat with citation-aware observations.
// --------------------------------------------------------------------------- //

function Console({ session, onTurn, focus, onRemoveFocus, onClearFocus }: {
  session: AnalysisSession; onTurn: () => void
  focus: FocusChip[]; onRemoveFocus: (cid: string) => void; onClearFocus: () => void
}) {
  const [messages, setMessages] = useState<AnalysisMessage[]>(session.messages ?? [])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  // Per-proposal outcome, keyed `${messageIdx}:${editIdx}`.
  const [resolved, setResolved] = useState<Record<string, 'applied' | 'dismissed'>>({})
  const [applying, setApplying] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => () => abortRef.current?.abort(), [])
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight }) }, [messages, status])

  const send = async () => {
    const text = input.trim()
    if (!text || busy) return
    const focusCids = focus.map((c) => c.cid)
    setInput(''); setBusy(true); setStatus('Analyzing…')
    setMessages((m) => [...m, {
      role: 'user', content: text,
      metadata: focusCids.length ? { focus: focusCids } : null,
      created_at: new Date().toISOString(),
    }])
    onClearFocus()
    const controller = new AbortController()
    abortRef.current = controller
    let hadError = false
    try {
      await streamChat(session.id, text, {
        onStatus: (msg) => setStatus(msg),
        onResult: (data) => {
          setMessages((m) => [...m, {
            role: 'assistant', content: data.assistant_text,
            metadata: {
              evidence_map: data.evidence_map, open_questions: data.open_questions,
              dropped_citations: data.dropped_citations, proposed_edits: data.proposed_edits,
            },
            created_at: new Date().toISOString(),
          }])
        },
        onError: (msg) => { hadError = true; setStatus(`⚠ ${msg}`) },
      }, controller.signal, focusCids)
    } finally {
      if (!controller.signal.aborted) {
        setBusy(false)
        if (!hadError) setStatus(null)
        onTurn()
      }
    }
  }

  // Apply a chat-proposed correction through the normal confirmed PATCH →
  // recompute path, using the CURRENT stored extraction (never the AI's copy).
  const applyEdit = async (edit: ProposedEdit, key: string) => {
    const ds = (session.datasets ?? []).find((d) => d.id === edit.dataset_id)
    const ext = ds?.extraction
    const idx = ext ? ext.periods.indexOf(edit.period) : -1
    const item = ext?.line_items.find((it) => it.label === edit.label)
    if (!ds || !ext || idx < 0 || !item) {
      setStatus('⚠ That figure no longer matches the stored extraction — review the dataset instead.')
      return
    }
    setApplying(key)
    try {
      await patchDataset(session.id, ds.id, {
        extraction: {
          ...ext,
          line_items: ext.line_items.map((it) =>
            it.label === edit.label
              ? { ...it, values: it.values.map((v, j) => (j === idx ? edit.proposed_value : v)) }
              : it),
        },
      })
      setResolved((r) => ({ ...r, [key]: 'applied' }))
      onTurn()
    } catch (e) {
      setStatus(`⚠ ${e instanceof Error ? e.message : 'Could not apply the correction.'}`)
    } finally {
      setApplying(null)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-sm text-zinc-600">
            Ask anything about your data — “Summarize this”, “What’s the trend?”, “Which is highest?”,
            “How volatile is this?”, “Compare the two periods.” Every number the pilot cites was computed
            from your data; anything it can’t trace is dropped. Click a record in the Metrics tab to focus
            the conversation on it.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
            <div className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-sm whitespace-pre-wrap ${
              m.role === 'user' ? 'bg-emerald-600 text-white' : 'bg-zinc-800/70 text-zinc-200'
            }`}>
              {m.content}
              {m.role === 'user' && (m.metadata?.focus?.length ?? 0) > 0 && (
                <div className="mt-1.5 text-[10px] text-emerald-200/80">
                  ⌖ focused on {m.metadata!.focus!.length} highlighted record{m.metadata!.focus!.length > 1 ? 's' : ''}
                </div>
              )}
              {m.role === 'assistant' && m.metadata?.evidence_map && m.metadata.evidence_map.length > 0 && (
                <div className="mt-2 pt-2 border-t border-zinc-700/60">
                  <div className="text-[11px] uppercase tracking-wide text-emerald-400/80 mb-1">Grounded observations</div>
                  <ul className="text-xs text-zinc-400 space-y-1">
                    {m.metadata.evidence_map.map((ob, j) => (
                      <li key={j}>• {ob.point} {ob.cited_ids.length > 0 && (
                        <span className="text-emerald-500/70">[{ob.cited_ids.length} cited]</span>
                      )}</li>
                    ))}
                  </ul>
                </div>
              )}
              {m.role === 'assistant' && m.metadata?.open_questions && m.metadata.open_questions.length > 0 && (
                <div className="mt-2 pt-2 border-t border-zinc-700/60">
                  <div className="text-[11px] uppercase tracking-wide text-amber-400/80 mb-1">Open questions</div>
                  <ul className="list-disc list-inside text-xs text-zinc-400 space-y-0.5">
                    {m.metadata.open_questions.map((q, j) => <li key={j}>{q}</li>)}
                  </ul>
                </div>
              )}
              {m.role === 'assistant' && (m.metadata?.proposed_edits?.length ?? 0) > 0 && (
                <div className="mt-2 pt-2 border-t border-zinc-700/60 space-y-2">
                  <div className="text-[11px] uppercase tracking-wide text-emerald-400/80">Proposed corrections</div>
                  {m.metadata!.proposed_edits!.map((edit, j) => {
                    const key = `${i}:${j}`
                    const state = resolved[key]
                    return (
                      <div key={j} className="rounded-lg border border-zinc-700/70 bg-zinc-900/50 px-2.5 py-2">
                        <div className="text-xs text-zinc-200">
                          {edit.label} · {edit.period}: <span className="line-through text-zinc-500">{edit.current_value ?? '—'}</span>
                          {' → '}<span className="text-emerald-400 font-medium">{edit.proposed_value}</span>
                        </div>
                        {edit.reason && <div className="text-[11px] text-zinc-500 mt-0.5">{edit.reason}</div>}
                        <div className="flex gap-2 mt-1.5">
                          {state === 'applied' ? (
                            <span className="text-[11px] text-emerald-400 inline-flex items-center gap-1"><Check className="h-3 w-3" /> Applied — metrics recomputed</span>
                          ) : state === 'dismissed' ? (
                            <span className="text-[11px] text-zinc-500">Dismissed</span>
                          ) : (
                            <>
                              <button onClick={() => void applyEdit(edit, key)} disabled={applying === key}
                                className="text-[11px] px-2 py-0.5 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white inline-flex items-center gap-1">
                                {applying === key ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />} Apply
                              </button>
                              <button onClick={() => setResolved((r) => ({ ...r, [key]: 'dismissed' }))}
                                className="text-[11px] px-2 py-0.5 rounded text-zinc-400 hover:text-zinc-200">Dismiss</button>
                            </>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        ))}
        {status && (
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> {status}
          </div>
        )}
      </div>
      <div className="p-3 border-t border-zinc-800">
        {focus.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 mb-2">
            {focus.map((c) => (
              <span key={c.cid} className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-300">
                <span className="truncate max-w-[220px]" title={c.label}>{c.label}</span>
                <button onClick={() => onRemoveFocus(c.cid)} className="text-emerald-400/70 hover:text-emerald-200">
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
            <button onClick={onClearFocus} className="text-[11px] text-zinc-500 hover:text-zinc-300">clear</button>
          </div>
        )}
        <div className="flex gap-2">
          <textarea value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }}
            placeholder={focus.length ? 'Ask about the highlighted records…' : 'Ask anything about your data…'} rows={2}
            className="flex-1 resize-none rounded-lg bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-zinc-200 focus:outline-none focus:border-emerald-500" />
          <button onClick={() => void send()} disabled={busy || !input.trim()}
            className="px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white self-stretch flex items-center">
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// NewSessionModal
// --------------------------------------------------------------------------- //

function NewSessionModal({ onClose, onCreated }: { onClose: () => void; onCreated: (s: AnalysisSession) => void }) {
  const [title, setTitle] = useState('')
  const [domain, setDomain] = useState('')
  const [goal, setGoal] = useState('')
  const [busy, setBusy] = useState(false)

  const create = async () => {
    if (!title.trim() || busy) return
    setBusy(true)
    try {
      const s = await createAnalysisSession({ title: title.trim(), domain: domain || undefined, goal: goal.trim() || undefined })
      onCreated(s)
    } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-950 p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-semibold text-zinc-100 mb-4 flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-emerald-500" /> New analysis
        </h3>
        <label className="block text-xs text-zinc-400 mb-1">Title</label>
        <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="Q3 portfolio volatility"
          className="w-full rounded-lg bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-zinc-200 mb-3 focus:outline-none focus:border-emerald-500" />
        <label className="block text-xs text-zinc-400 mb-1">Domain <span className="text-zinc-600">(optional)</span></label>
        <select value={domain} onChange={(e) => setDomain(e.target.value)}
          className="w-full rounded-lg bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-zinc-200 mb-3">
          <option value="">General</option>
          <option value="financial">Financial</option>
          <option value="insurance">Insurance / P&C</option>
          <option value="sports">Sports</option>
          <option value="operations">Operations / Inventory</option>
        </select>
        <label className="block text-xs text-zinc-400 mb-1">What do you want to understand? <span className="text-zinc-600">(optional)</span></label>
        <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3}
          placeholder="e.g. What's the revenue trend? How volatile are these returns?"
          className="w-full rounded-lg bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-zinc-200 mb-4 focus:outline-none focus:border-emerald-500" />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-2 text-sm text-zinc-400 hover:text-zinc-200">Cancel</button>
          <button onClick={() => void create()} disabled={!title.trim() || busy}
            className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-medium inline-flex items-center gap-2">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Create
          </button>
        </div>
      </div>
    </div>
  )
}
