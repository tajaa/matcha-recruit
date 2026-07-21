import { useState } from 'react'
import { api } from '../../../api/client'
import { Modal } from '../../../components/ui'

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
    <Modal open onClose={onClose} title="Import subscribers" width="lg" dismissible={!busy}>
        <p className="text-xs text-zinc-500 mb-3">
          Paste CSV. First column = email, optional second column = name. Header row optional. Up to 500 rows per import.
        </p>
        <textarea
          value={csv}
          onChange={(e) => setCsv(e.target.value)}
          placeholder={'email,name\nsam@example.com,Sam Lee\nalex@example.com,Alex Park'}
          rows={10}
          className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-xs font-mono text-zinc-200 placeholder-zinc-500 outline-none"
        />
        <p className="text-[10px] text-zinc-500 mt-2">Detected: {parseCsv().length} valid email(s)</p>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="text-xs px-3 py-1.5 rounded-lg text-zinc-400 hover:text-zinc-200">Cancel</button>
          <button onClick={submit} disabled={busy || parseCsv().length === 0} className="text-xs px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40">
            {busy ? 'Importing…' : 'Import'}
          </button>
        </div>
    </Modal>
  )
}
