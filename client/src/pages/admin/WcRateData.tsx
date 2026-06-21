import { useEffect, useState, type ChangeEvent } from 'react'
import { Loader2, Upload, Download, Database } from 'lucide-react'
import { Card } from '../../components/ui'
import {
  fetchWcRateSummary, importWcStateRates, importWcClassCodes, downloadWcRateTemplate,
  type WcRateSummary, type ImportResult,
} from '../../api/wcRates'

// Admin tool to load a licensed NCCI / state-bureau WC rate feed via CSV,
// replacing the illustrative demo seed used by the broker WC surfaces.
export default function WcRateData() {
  const [summary, setSummary] = useState<WcRateSummary | null>(null)
  const [loading, setLoading] = useState(true)

  function load() {
    setLoading(true)
    fetchWcRateSummary().then(setSummary).catch(() => setSummary(null)).finally(() => setLoading(false))
  }
  useEffect(load, [])

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <Database className="h-5 w-5 text-zinc-400" /> WC Rate Data
        </h1>
        <p className="text-sm text-zinc-500 mt-1">Load a licensed NCCI / state-bureau feed via CSV. This replaces the illustrative demo seed the broker Workers'-Comp surfaces read (state loss-cost trends + class-code base rates). The rate data is licensed — supply your own export.</p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-32"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          <SourceCard title="State rate rows" counts={summary?.state_rates ?? {}} />
          <SourceCard title="Class-code rows" counts={summary?.class_codes ?? {}} />
        </div>
      )}

      <ImportCard
        title="State loss-cost rates"
        desc="CSV: state, loss_cost_change_pct, effective_date, trend (optional), note (optional). Upserts on state + effective date."
        kind="state-rates"
        doImport={importWcStateRates}
        onDone={load}
      />
      <ImportCard
        title="Class-code base rates"
        desc="CSV: state (optional, default US), class_code, description, base_rate. Upserts on state + class code."
        kind="class-codes"
        doImport={importWcClassCodes}
        onDone={load}
      />
    </div>
  )
}

function SourceCard({ title, counts }: { title: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts)
  const total = entries.reduce((s, [, n]) => s + n, 0)
  return (
    <Card className="p-4">
      <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold">{title}</div>
      <div className="text-2xl font-light font-mono mt-1.5 text-zinc-200">{total}</div>
      <div className="mt-2 space-y-0.5">
        {entries.length === 0 ? <div className="text-[11px] text-zinc-600">none</div> : entries.map(([src, n]) => (
          <div key={src} className="flex items-center justify-between text-[11px]">
            <span className={src.includes('seed') ? 'text-amber-400' : 'text-emerald-400'}>{src}</span>
            <span className="font-mono text-zinc-400">{n}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}

function ImportCard({ title, desc, kind, doImport, onDone }: {
  title: string; desc: string; kind: 'state-rates' | 'class-codes'
  doImport: (f: File, source: string) => Promise<ImportResult>; onDone: () => void
}) {
  const [source, setSource] = useState('ncci-import')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBusy(true); setResult(null)
    try {
      setResult(await doImport(file, source.trim() || 'ncci-import'))
      onDone()
    } catch {
      setResult({ imported: 0, errors: ['Upload failed.'] })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-medium text-zinc-200 tracking-wide">{title}</h3>
        <button onClick={() => downloadWcRateTemplate(kind)} className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200">
          <Download className="h-3.5 w-3.5" /> CSV template
        </button>
      </div>
      <p className="text-[11px] text-zinc-500 mb-3">{desc}</p>
      <div className="flex items-center gap-2">
        <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="source label"
          className="bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 w-40 focus:outline-none focus:border-zinc-500" />
        <label className={`inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border ${busy ? 'text-zinc-500 border-zinc-800 cursor-wait' : 'text-zinc-900 bg-zinc-100 hover:bg-white border-transparent cursor-pointer'}`}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} {busy ? 'Importing…' : 'Upload CSV'}
          <input type="file" accept=".csv,text/csv" className="hidden" disabled={busy} onChange={onFile} />
        </label>
      </div>
      {result && (
        <div className="mt-3 text-xs">
          <span className="text-emerald-400">{result.imported} rows imported.</span>
          {result.errors.length > 0 && (
            <ul className="mt-1 text-red-400 space-y-0.5">{result.errors.map((er, i) => <li key={i}>{er}</li>)}</ul>
          )}
        </div>
      )}
    </Card>
  )
}
