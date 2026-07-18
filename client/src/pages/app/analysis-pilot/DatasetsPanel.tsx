import { useEffect, useState } from 'react'
import { FileSpreadsheet, FileText, Loader2, RefreshCw, Trash2 } from 'lucide-react'
import { FileUpload } from '../../../components/ui/FileUpload'
import { HelpHint } from '../../../components/ui/HelpHint'
import {
  uploadDataset, patchDataset, deleteDataset,
  type AnalysisSession, type AnalysisDataset,
} from '../../../api/analysis-pilot/analysisPilot'
import { type FocusChip } from './shared'
import { MappingModal } from './MappingModal'

// --------------------------------------------------------------------------- //
// Datasets panel — upload + list + review/mapping + delete.
// --------------------------------------------------------------------------- //

export function DatasetsPanel({ session, onChange, onFocus }: {
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
        <span className="text-sm font-semibold text-zinc-200 inline-flex items-center gap-1.5">
          Datasets
          <HelpHint text="ready = analyzed and citable · review = confirm the extracted figures first · processing = still analyzing · failed = re-upload or check the file." />
        </span>
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
