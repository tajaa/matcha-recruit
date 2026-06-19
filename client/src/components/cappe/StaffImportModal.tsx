// CSV import for a site's staff / employees. Explains how to prepare the file,
// offers a ready-made template (seeded with the site's real branch names), maps
// a `branch` column to a location so each employee auto-lands at the right
// branch, and shows a per-row outcome summary.
import { useRef, useState } from 'react'
import { AlertTriangle, Check, Download, FileSpreadsheet, Loader2, Upload, X } from 'lucide-react'
import { cappeApi } from '../../api/cappeClient'
import type { CappeLocation, CappeStaffImportResult } from '../../types/cappe'

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

export default function StaffImportModal({ siteId, locations, multiBranch, onClose, onImported }: {
  siteId: string
  locations: CappeLocation[]
  // Whether this site runs multiple locations (the site's is_multi_location
  // flag) — drives the branch-column guidance + template.
  multiBranch: boolean
  onClose: () => void
  onImported: (r: CappeStaffImportResult) => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<CappeStaffImportResult | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const branchNames = locations.map((l) => l.name)

  function template() {
    // Single-location sites get a simpler template with no branch column; multi
    // seeds branch with the business's real branch names so the spelling is obvious.
    if (!multiBranch) {
      downloadCsv('cappe-staff-template.csv', [
        ['name', 'bio', 'active'],
        ['Maria Lopez', 'Senior stylist', 'yes'],
        ['Jordan Kim', 'Barber', 'yes'],
      ])
      return
    }
    const b1 = branchNames[0] || ''
    const b2 = branchNames[1] || branchNames[0] || ''
    downloadCsv('cappe-staff-template.csv', [
      ['name', 'branch', 'bio', 'active'],
      ['Maria Lopez', b1, 'Senior stylist', 'yes'],
      ['Jordan Kim', b2, 'Barber', 'yes'],
    ])
  }

  async function submit() {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const r = await cappeApi.upload<CappeStaffImportResult>(`/sites/${siteId}/staff/import`, fd)
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
              <FileSpreadsheet className="h-5 w-5 text-emerald-400" /> Import staff
            </h2>
            <p className="mt-0.5 text-sm text-zinc-400">Bring your team in from a CSV — each person mapped to their branch.</p>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200"><X className="h-5 w-5" /></button>
        </div>

        {result ? (
          <div className="space-y-4">
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
              <p className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
                <Check className="h-4 w-4" /> Imported {result.created + result.updated} of {result.total} rows
              </p>
              <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-zinc-400">
                <span>Added: <b className="text-zinc-200">{result.created}</b></span>
                <span>Updated: <b className="text-zinc-200">{result.updated}</b></span>
                <span>Skipped: <b className="text-zinc-200">{result.skipped}</b></span>
                <span>Branch-mapped: <b className="text-zinc-200">{result.branches_matched}</b></span>
              </div>
            </div>
            {result.errors.length > 0 && (
              <div className="rounded-xl border border-amber-700/40 bg-amber-500/[0.06] p-4">
                <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-amber-300">
                  <AlertTriangle className="h-3.5 w-3.5" /> {result.errors.length} row{result.errors.length > 1 ? 's' : ''} skipped
                </p>
                <ul className="max-h-40 space-y-1 overflow-y-auto text-xs text-amber-200/90">
                  {result.errors.slice(0, 50).map((er, i) => (
                    <li key={i}>Row {er.row}{er.name ? ` (${er.name})` : ''}: {er.reason}</li>
                  ))}
                  {result.errors.length > 50 && <li className="text-amber-300/70">…and {result.errors.length - 50} more.</li>}
                </ul>
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button onClick={() => { setResult(null); setFile(null) }} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800">Import another</button>
              <button onClick={onClose} className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400">Done</button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* prep instructions */}
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4 text-sm text-zinc-300">
              <p className="mb-2 font-medium text-zinc-100">How to prepare your CSV</p>
              <ul className="list-disc space-y-1.5 pl-4 text-xs text-zinc-400">
                <li>First row must be headers. Columns: <code className="text-zinc-200">name</code> (required), {multiBranch && <><code className="text-zinc-200">branch</code>, </>}<code className="text-zinc-200">bio</code>, <code className="text-zinc-200">active</code>.</li>
                {multiBranch ? (
                  <li><b className="text-zinc-300">branch</b> must exactly match one of your branch names (case doesn't matter) — this is how each employee is mapped to their location. Leave it blank for someone who works at all locations.</li>
                ) : (
                  <li>You have a single location, so the <b className="text-zinc-300">branch</b> column is optional — leave it out or blank.</li>
                )}
                <li><b className="text-zinc-300">active</b> — <code className="text-zinc-200">no</code> hides them from booking; anything else (or blank) keeps them active.</li>
                <li>Re-importing the same name updates that person’s branch/bio (no duplicates).</li>
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
              <button onClick={template} className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-400 hover:text-emerald-300">
                <Download className="h-3.5 w-3.5" /> Download template
              </button>
            </div>

            {/* file picker */}
            <div>
              <input ref={inputRef} type="file" accept=".csv,text/csv" className="hidden"
                onChange={(e) => { setFile(e.target.files?.[0] || null); setError(null) }} />
              <button onClick={() => inputRef.current?.click()}
                className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-zinc-700 py-4 text-sm font-medium text-zinc-300 hover:border-emerald-500 hover:text-emerald-400">
                <Upload className="h-4 w-4" /> {file ? file.name : 'Choose a CSV file'}
              </button>
            </div>

            {error && <p className="text-sm text-red-400">{error}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-zinc-800">Cancel</button>
              <button onClick={submit} disabled={!file || busy}
                className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Import
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
