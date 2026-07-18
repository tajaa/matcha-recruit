import { useState, type ChangeEvent } from 'react'
import { Upload, Download, Loader2, X, Check, AlertCircle, Sparkles, Trash2 } from 'lucide-react'
import { downloadBuildingTemplate, bulkUploadBuildings, parseSovFile, bulkInsertBuildings } from '../../api/risk/property'
import type { BuildingPayload, BulkUploadResult, ConstructionType } from '../../types/property'
import { CONSTRUCTION_LABEL } from '../../types/property'

const CONSTRUCTION_OPTS: ConstructionType[] = ['fire_resistive', 'modified_fire_resistive', 'masonry_non_combustible', 'non_combustible', 'joisted_masonry', 'frame']
const inp = 'w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500'
const numOrNull = (v: string) => { const n = parseFloat(v); return Number.isFinite(n) ? n : null }

type Tab = 'csv' | 'parse'

export function SovImportModal({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [tab, setTab] = useState<Tab>('csv')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<BulkUploadResult | null>(null)
  const [parsed, setParsed] = useState<BuildingPayload[] | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  async function onCsvFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBusy(true); setMsg(null); setResult(null)
    try { setResult(await bulkUploadBuildings(file)); onImported() }
    catch (err) { setMsg(err instanceof Error ? err.message : 'Upload failed') }
    finally { setBusy(false) }
  }

  async function onParseFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBusy(true); setMsg(null); setParsed(null); setResult(null)
    try {
      const r = await parseSovFile(file)
      if (!r.available || !r.buildings.length) setMsg("Couldn't read any buildings from that file — try the CSV template instead.")
      else setParsed(r.buildings)
    } catch (err) { setMsg(err instanceof Error ? err.message : 'Parse failed') }
    finally { setBusy(false) }
  }

  function editParsed(i: number, patch: Partial<BuildingPayload>) {
    setParsed((prev) => (prev ? prev.map((b, idx) => (idx === i ? { ...b, ...patch } : b)) : prev))
  }
  function removeParsed(i: number) {
    setParsed((prev) => (prev ? prev.filter((_, idx) => idx !== i) : prev))
  }

  async function confirmImport() {
    if (!parsed?.length) return
    setBusy(true); setMsg(null)
    try { setResult(await bulkInsertBuildings(parsed)); setParsed(null); onImported() }
    catch (err) { setMsg(err instanceof Error ? err.message : 'Import failed') }
    finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-3xl max-h-[88vh] overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-zinc-200">Import Statement of Values</h3>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200"><X className="h-4 w-4" /></button>
        </div>

        <div className="flex gap-1 mb-4 text-xs">
          <button onClick={() => { setTab('csv'); setMsg(null) }}
            className={`px-3 py-1.5 rounded-lg border transition-colors ${tab === 'csv' ? 'border-zinc-500 text-zinc-100 bg-zinc-900' : 'border-zinc-800 text-zinc-500 hover:text-zinc-300'}`}>
            CSV upload
          </button>
          <button onClick={() => { setTab('parse'); setMsg(null) }}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-colors ${tab === 'parse' ? 'border-emerald-500/40 text-emerald-300 bg-emerald-500/[0.06]' : 'border-zinc-800 text-zinc-500 hover:text-zinc-300'}`}>
            <Sparkles className="h-3 w-3" /> Parse a file (AI)
          </button>
        </div>

        {tab === 'csv' && (
          <div className="space-y-3">
            <p className="text-[12px] text-zinc-400">Download the template, fill one building per row, and upload. Unknown construction types import blank — edit them afterward.</p>
            <div className="flex items-center gap-2">
              <button onClick={() => downloadBuildingTemplate()} className="inline-flex items-center gap-1.5 text-xs text-zinc-200 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500">
                <Download className="h-3.5 w-3.5" /> Download template
              </button>
              <label className="inline-flex items-center gap-1.5 text-xs text-zinc-200 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 cursor-pointer">
                <Upload className="h-3.5 w-3.5" /> Upload CSV
                <input type="file" accept=".csv" className="hidden" onChange={onCsvFile} disabled={busy} />
              </label>
              {busy && <Loader2 className="h-4 w-4 animate-spin text-zinc-500" />}
            </div>
          </div>
        )}

        {tab === 'parse' && (
          <div className="space-y-3">
            <p className="text-[12px] text-zinc-400">Upload a carrier SOV (PDF or CSV). AI extracts the buildings into a list you review and edit before importing. Export spreadsheets to CSV first.</p>
            {!parsed && (
              <label className="inline-flex items-center gap-1.5 text-xs text-zinc-200 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 cursor-pointer w-fit">
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />} {busy ? 'Reading…' : 'Upload SOV (PDF / CSV)'}
                <input type="file" accept=".pdf,.csv,.txt,.tsv" className="hidden" onChange={onParseFile} disabled={busy} />
              </label>
            )}

            {parsed && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[12px] text-zinc-400">{parsed.length} building(s) parsed — review and edit, then import.</span>
                  <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400/70"><Sparkles className="h-3 w-3" /> AI-extracted — verify before importing</span>
                </div>
                <div className="overflow-x-auto rounded-lg border border-zinc-800">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="bg-zinc-900/60 text-[10px] text-zinc-500 uppercase tracking-wider">
                        <th className="px-2 py-1.5">Name</th>
                        <th className="px-2 py-1.5">City / ST</th>
                        <th className="px-2 py-1.5">Construction</th>
                        <th className="px-2 py-1.5 text-right">Building $</th>
                        <th className="px-2 py-1.5 text-right">Insured $</th>
                        <th className="px-2 py-1.5 text-center">Spr</th>
                        <th className="px-2 py-1.5"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {parsed.map((b, i) => (
                        <tr key={i} className="border-t border-zinc-800/60">
                          <td className="px-2 py-1"><input className={inp} value={b.name ?? ''} onChange={(e) => editParsed(i, { name: e.target.value || null })} /></td>
                          <td className="px-2 py-1">
                            <div className="flex gap-1">
                              <input className={inp} value={b.city ?? ''} onChange={(e) => editParsed(i, { city: e.target.value || null })} />
                              <input className={`${inp} w-12`} maxLength={2} value={b.state ?? ''} onChange={(e) => editParsed(i, { state: e.target.value.toUpperCase().slice(0, 2) || null })} />
                            </div>
                          </td>
                          <td className="px-2 py-1">
                            <select className={inp} value={b.construction_type ?? ''} onChange={(e) => editParsed(i, { construction_type: (e.target.value || null) as ConstructionType | null })}>
                              <option value="">—</option>
                              {CONSTRUCTION_OPTS.map((c) => <option key={c} value={c}>{CONSTRUCTION_LABEL[c]}</option>)}
                            </select>
                          </td>
                          <td className="px-2 py-1"><input className={`${inp} text-right`} type="number" value={b.building_value ?? ''} onChange={(e) => editParsed(i, { building_value: numOrNull(e.target.value) })} /></td>
                          <td className="px-2 py-1"><input className={`${inp} text-right`} type="number" value={b.insured_value ?? ''} onChange={(e) => editParsed(i, { insured_value: numOrNull(e.target.value) })} /></td>
                          <td className="px-2 py-1 text-center"><input type="checkbox" checked={b.sprinklered} onChange={(e) => editParsed(i, { sprinklered: e.target.checked })} /></td>
                          <td className="px-2 py-1 text-right"><button onClick={() => removeParsed(i)} className="text-zinc-600 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={confirmImport} disabled={busy || !parsed.length} className="inline-flex items-center gap-1.5 bg-zinc-100 text-zinc-900 text-xs font-medium rounded-lg px-3 py-1.5 hover:bg-white disabled:opacity-50">
                    {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Import {parsed.length} building(s)
                  </button>
                  <button onClick={() => { setParsed(null); setMsg(null) }} className="text-xs text-zinc-500 hover:text-zinc-300 px-2">Discard</button>
                </div>
              </div>
            )}
          </div>
        )}

        {msg && <p className="mt-3 flex items-start gap-1.5 text-[12px] text-amber-400"><AlertCircle className="h-3.5 w-3.5 mt-px shrink-0" />{msg}</p>}

        {result && (
          <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2.5">
            <p className="text-[12px] text-zinc-200">
              <span className="text-emerald-400 font-medium">{result.created} imported</span>
              {result.failed > 0 && <span className="text-amber-400"> · {result.failed} failed</span>}
            </p>
            {result.errors.length > 0 && (
              <ul className="mt-1 space-y-0.5 max-h-32 overflow-y-auto">
                {result.errors.map((er, i) => (
                  <li key={i} className="text-[11px] text-zinc-500">Row {er.row} {er.name && `(${er.name})`}: {er.error}</li>
                ))}
              </ul>
            )}
            <button onClick={onClose} className="mt-2 text-xs text-zinc-400 hover:text-zinc-200">Done</button>
          </div>
        )}
      </div>
    </div>
  )
}
