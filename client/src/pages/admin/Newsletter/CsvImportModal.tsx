import { useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../../../api/client'

export function CsvImportModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [csv, setCsv] = useState('')
  const [busy, setBusy] = useState(false)

  function parseCsv(): { email: string; name?: string }[] {
    // Handles quoted fields with embedded commas + escaped doubled quotes,
    // e.g.: '"Sam, Jr.",sam@x.com' → ['Sam, Jr.', 'sam@x.com'].
    function parseRow(row: string): string[] {
      const out: string[] = []
      let cur = ''
      let inQuotes = false
      for (let i = 0; i < row.length; i++) {
        const ch = row[i]
        if (inQuotes) {
          if (ch === '"') {
            if (row[i + 1] === '"') { cur += '"'; i++ } // escaped ""
            else inQuotes = false
          } else {
            cur += ch
          }
        } else if (ch === '"') {
          inQuotes = true
        } else if (ch === ',') {
          out.push(cur)
          cur = ''
        } else {
          cur += ch
        }
      }
      out.push(cur)
      return out.map((p) => p.trim())
    }

    const rows = csv.replace(/\r\n/g, '\n').split('\n').map((r) => r.trim()).filter(Boolean)
    if (!rows.length) return []
    const start = rows[0].toLowerCase().includes('email') ? 1 : 0
    return rows.slice(start)
      .map(parseRow)
      .filter((parts) => parts.length >= 1)
      .map((parts) => ({ email: (parts[0] || '').toLowerCase(), name: parts[1] || undefined }))
      .filter((p) => p.email.includes('@'))
  }

  async function submit() {
    const emails = parseCsv()
    if (emails.length === 0) {
      alert('No valid emails parsed.')
      return
    }
    setBusy(true)
    try {
      const res = await api.post<{ imported: number }>('/admin/newsletter/subscribers/import', { emails })
      alert(`Imported ${res.imported} subscriber(s).`)
      onDone()
    } catch (err) {
      alert(`Import failed: ${(err as Error).message}`)
    }
    setBusy(false)
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200 rounded-xl shadow-xl p-6 w-full max-w-2xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-900">Import subscribers</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700"><X size={16} /></button>
        </div>
        <p className="text-xs text-slate-500 mb-3">
          Paste CSV. First column = email, optional second column = name. Header row optional. Up to 500 rows per import.
        </p>
        <textarea
          value={csv}
          onChange={(e) => setCsv(e.target.value)}
          placeholder={'email,name\nsam@example.com,Sam Lee\nalex@example.com,Alex Park'}
          rows={10}
          className="w-full px-3 py-2 rounded-lg border border-slate-300 bg-slate-50 text-xs font-mono text-slate-800 placeholder-slate-400 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 transition-colors"
        />
        <p className="text-[10px] text-slate-400 mt-2">Detected: {parseCsv().length} valid email(s)</p>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="text-xs px-3 py-1.5 rounded-lg text-slate-500 hover:text-slate-800">Cancel</button>
          <button onClick={submit} disabled={busy || parseCsv().length === 0} className="text-xs px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm disabled:opacity-40">
            {busy ? 'Importing…' : 'Import'}
          </button>
        </div>
      </div>
    </div>
  )
}
