// CSV import for a site's existing clientele. Explains how to prepare the file,
// offers a ready-made template (seeded with the site's real branch names), maps
// a `branch` column to a location, and shows a per-row outcome summary.
import { useRef, useState } from 'react'
import { AlertTriangle, Check, Download, FileSpreadsheet, Loader2, Upload, X } from 'lucide-react'
import { cappeApi } from '../api'
import type { CappeClientImportResult, CappeLocation } from '../types'

function downloadCsv(filename: string, rows: string[][]) {
  // Quote every cell so commas/quotes in names survive round-trip.
  const esc = (v: string) => `"${(v ?? '').replace(/"/g, '""')}"`
  const csv = rows.map((r) => r.map(esc).join(',')).join('\r\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export default function ClientImportModal({ siteId, locations, multiBranch, onClose, onImported }: {
  siteId: string
  locations: CappeLocation[]
  // Whether this site runs multiple locations (the site's is_multi_location
  // flag, set in onboarding) — drives the branch-column guidance + template.
  multiBranch: boolean
  onClose: () => void
  onImported: (r: CappeClientImportResult) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [addToNewsletter, setAddToNewsletter] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<CappeClientImportResult | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const branchNames = locations.map((l) => l.name)

  function template() {
    // Use reserved (non-deliverable) example domains. Single-location sites get
    // a simpler template with no branch column; multi seeds branch with the
    // business's real branch names so the spelling is obvious.
    if (!multiBranch) {
      downloadCsv('cappe-clients-template.csv', [
        ['email', 'name', 'phone', 'notes', 'tags'],
        ['jane.doe@example.com', 'Jane Doe', '555-0100', 'VIP regular', 'vip;loyal'],
        ['john.smith@example.org', 'John Smith', '555-0101', '', 'new'],
      ])
      return
    }
    const b1 = branchNames[0] || ''
    const b2 = branchNames[1] || branchNames[0] || ''
    downloadCsv('cappe-clients-template.csv', [
      ['email', 'name', 'phone', 'branch', 'notes', 'tags'],
      ['jane.doe@example.com', 'Jane Doe', '555-0100', b1, 'VIP regular', 'vip;loyal'],
      ['john.smith@example.org', 'John Smith', '555-0101', b2, '', 'new'],
    ])
  }

  async function submit() {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('add_to_newsletter', addToNewsletter ? 'true' : 'false')
      const r = await cappeApi.upload<CappeClientImportResult>(`/sites/${siteId}/clients/import`, fd)
      setResult(r)
      onImported(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="max-h-[88vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-zinc-700 bg-zinc-900 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold text-zinc-50">
              <FileSpreadsheet className="h-5 w-5 text-lime-400" /> Import clients
            </h2>
            <p className="mt-0.5 text-sm text-zinc-400">Bring your existing client list in from a CSV.</p>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200"><X className="h-5 w-5" /></button>
        </div>

        {result ? (
          <div className="space-y-4">
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
              <p className="flex items-center gap-2 text-sm font-semibold text-lime-400">
                <Check className="h-4 w-4" /> Imported {result.created + result.updated} of {result.total} rows
              </p>
              <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-zinc-400">
                <span>Added: <b className="text-zinc-200">{result.created}</b></span>
                <span>Updated: <b className="text-zinc-200">{result.updated}</b></span>
                <span>Skipped: <b className="text-zinc-200">{result.skipped}</b></span>
                <span>Branch-mapped: <b className="text-zinc-200">{result.branches_matched}</b></span>
                {result.newsletter_added > 0 && <span className="col-span-2">Added to newsletter: <b className="text-zinc-200">{result.newsletter_added}</b></span>}
              </div>
            </div>
            {result.errors.length > 0 && (
              <div className="rounded-xl border border-amber-700/40 bg-amber-500/[0.06] p-4">
                <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-amber-300">
                  <AlertTriangle className="h-3.5 w-3.5" /> {result.errors.length} row{result.errors.length > 1 ? 's' : ''} skipped
                </p>
                <ul className="max-h-40 space-y-1 overflow-y-auto text-xs text-amber-200/90">
                  {result.errors.slice(0, 50).map((er, i) => (
                    <li key={i}>Row {er.row}{er.email ? ` (${er.email})` : ''}: {er.reason}</li>
                  ))}
                  {result.errors.length > 50 && <li className="text-amber-300/70">…and {result.errors.length - 50} more.</li>}
                </ul>
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button onClick={() => { setResult(null); setFile(null) }} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800">Import another</button>
              <button onClick={onClose} className="rounded-lg bg-lime-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-400">Done</button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* prep instructions */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4 text-sm text-zinc-300">
              <p className="mb-2 font-medium text-zinc-100">How to prepare your CSV</p>
              <ul className="list-disc space-y-1.5 pl-4 text-xs text-zinc-400">
                <li>First row must be headers. Columns: <code className="text-zinc-200">email</code> (required), <code className="text-zinc-200">name</code>, <code className="text-zinc-200">phone</code>, {multiBranch && <><code className="text-zinc-200">branch</code>, </>}<code className="text-zinc-200">notes</code>, <code className="text-zinc-200">tags</code>.</li>
                <li>Tags in one cell, separated by <code className="text-zinc-200">;</code> (e.g. <span className="text-zinc-300">vip;loyal</span>).</li>
                {multiBranch ? (
                  <li><b className="text-zinc-300">branch</b> must exactly match one of your branch names (case doesn't matter). Leave it blank for your main location.</li>
                ) : (
                  <li>You have a single location, so the <b className="text-zinc-300">branch</b> column is optional — leave it out or blank.</li>
                )}
                <li>Re-importing the same email updates that client (no duplicates).</li>
              </ul>
              {multiBranch && (
                <div className="mt-3">
                  <p className="mb-1 text-[11px] font-medium text-zinc-400">Your branches (use these exact names):</p>
                  <div className="flex flex-wrap gap-1.5">
                    {branchNames.map((n) => (
                      <span key={n} className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-xs text-zinc-200">{n}</span>
                    ))}
                  </div>
                </div>
              )}
              <button onClick={template} className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-lime-400 hover:text-lime-300">
                <Download className="h-3.5 w-3.5" /> Download template
              </button>
            </div>

            {/* file picker */}
            <div>
              <input ref={inputRef} type="file" accept=".csv,text/csv" className="hidden"
                onChange={(e) => { setFile(e.target.files?.[0] || null); setError(null) }} />
              <button onClick={() => inputRef.current?.click()}
                className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-zinc-700 py-4 text-sm font-medium text-zinc-300 hover:border-lime-500 hover:text-lime-400">
                <Upload className="h-4 w-4" /> {file ? file.name : 'Choose a CSV file'}
              </button>
            </div>

            {/* newsletter opt-in */}
            <label className="flex items-start gap-2 text-sm text-zinc-300">
              <input type="checkbox" checked={addToNewsletter} onChange={(e) => setAddToNewsletter(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-zinc-600 bg-zinc-900 text-lime-500" />
              <span>Also add these clients to my newsletter list.
                <span className="block text-xs text-zinc-500">Only do this if they’ve agreed to hear from you. Off by default.</span>
              </span>
            </label>

            {error && <p className="text-sm text-red-400">{error}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800">Cancel</button>
              <button onClick={submit} disabled={!file || busy}
                className="flex items-center gap-2 rounded-lg bg-lime-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-lime-400 disabled:opacity-60">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Import
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
