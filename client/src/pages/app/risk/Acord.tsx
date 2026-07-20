import { useState } from 'react'
import { FileDown, Loader2, FileText } from 'lucide-react'
import { Card } from '../../../components/ui'
import { useAsync } from '../../../hooks/useAsync'
import { listAcordForms, downloadAcord } from '../../../api/risk/acord'

export default function Acord() {
  const { data: forms, loading } = useAsync(() => listAcordForms().then((r) => r.forms), [], [])
  const [dl, setDl] = useState<string | null>(null)

  async function download(form: string) {
    setDl(form)
    try { await downloadAcord(form) } finally { setDl(null) }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
          <FileText className="h-5 w-5 text-zinc-400" /> ACORD Forms
        </h1>
        <p className="text-sm text-zinc-500 mt-1 max-w-2xl">Generate branded ACORD 125/126/130/140 equivalents from data already on file (Statement of Values, WC class exposures, company profile). Not official facsimiles — same field set, carrier-ready.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {(forms || []).map((f) => (
          <Card key={f.form} className="p-4 flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-medium text-zinc-200">ACORD {f.form}</div>
              <div className="text-xs text-zinc-500">{f.label}</div>
            </div>
            <button onClick={() => download(f.form)} disabled={dl === f.form} className="inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-2 font-medium disabled:opacity-50">
              {dl === f.form ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />} PDF
            </button>
          </Card>
        ))}
      </div>
    </div>
  )
}
