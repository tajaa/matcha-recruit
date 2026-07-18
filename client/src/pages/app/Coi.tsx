import { useEffect, useRef, useState } from 'react'
import { FileText, Loader2, Upload, Trash2 } from 'lucide-react'
import { Card } from '../../components/ui'
import { listCois, uploadCoi, deleteCoi, type CoiList, type CoiStatus } from '../../api/risk/coi'

const STATUS_TONE: Record<CoiStatus, string> = {
  active: 'text-emerald-400', expiring: 'text-amber-400', expired: 'text-rose-400', unknown: 'text-zinc-500',
}

export default function Coi() {
  const [data, setData] = useState<CoiList | null>(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => { listCois().then(setData).finally(() => setLoading(false)) }, [])

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try { setData(await uploadCoi(file)) } finally { setUploading(false); if (fileRef.current) fileRef.current.value = '' }
  }

  async function remove(id: string) {
    setData(await deleteCoi(id))
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 text-zinc-500 animate-spin" /></div>
  if (!data) return <p className="text-sm text-zinc-500">Unable to load certificates.</p>

  const s = data.summary
  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
            <FileText className="h-5 w-5 text-zinc-400" /> Certificate Tracking
          </h1>
          <p className="text-sm text-zinc-500 mt-1 max-w-2xl">Upload inbound certificates of insurance — carrier, limits, and expiry are extracted, auto-verified against required limits, and tracked for renewal.</p>
        </div>
        <div>
          <input ref={fileRef} type="file" accept="application/pdf" onChange={onFile} className="hidden" />
          <button onClick={() => fileRef.current?.click()} disabled={uploading} className="inline-flex items-center gap-1.5 text-sm text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-2 font-medium disabled:opacity-50">
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Upload COI
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {([['total', 'Total'], ['active', 'Active'], ['expiring', 'Expiring'], ['expired', 'Expired'], ['with_gaps', 'Limit gaps']] as const).map(([k, label]) => (
          <Card key={k} className="p-3">
            <div className="text-xs text-zinc-500">{label}</div>
            <div className="text-xl font-semibold text-zinc-100">{s[k as keyof typeof s]}</div>
          </Card>
        ))}
      </div>

      <Card className="p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
            <th className="py-2.5 px-4">Holder / Carrier</th><th>Lines</th><th>Expiry</th><th>Status</th><th>Verify</th><th></th>
          </tr></thead>
          <tbody>
            {data.certificates.length === 0 && <tr><td colSpan={6} className="px-4 py-6 text-zinc-600">No certificates yet — upload one.</td></tr>}
            {data.certificates.map((c) => (
              <tr key={c.id} className="border-b border-zinc-900">
                <td className="px-4 py-2.5 text-zinc-200">{c.holder_name || '—'}<div className="text-xs text-zinc-500">{c.carrier || (c.ai_available ? '' : 'not extracted')}</div></td>
                <td className="text-zinc-400">{c.lines.length}</td>
                <td className="text-zinc-400">{c.expiry_date || '—'}</td>
                <td className={STATUS_TONE[c.status]}>{c.status}</td>
                <td className="text-zinc-400">{c.verification?.summary?.contract_shortfalls ? <span className="text-rose-400">{c.verification.summary.contract_shortfalls} short</span> : c.verification ? <span className="text-emerald-400">ok</span> : '—'}</td>
                <td className="pr-4 text-right"><button onClick={() => remove(c.id)} className="text-zinc-600 hover:text-rose-400"><Trash2 className="h-4 w-4" /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
