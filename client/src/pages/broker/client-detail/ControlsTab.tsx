import { useState } from 'react'
import { FileDown, Loader2 } from 'lucide-react'
import { Card } from '../../../components/ui'
import { useAsync } from '../../../hooks/useAsync'
import { fetchClientControls, downloadClientControls } from '../../../api/broker/broker'

export function ControlsTab({ companyId }: { companyId: string }) {
  const { data: reg, loading } = useAsync(() => fetchClientControls(companyId), [companyId], null)
  const [dl, setDl] = useState(false)

  const tone = (s: string) =>
    s === 'strong' ? 'text-emerald-400' : s === 'partial' ? 'text-amber-400' : s === 'gap' ? 'text-red-400' : 'text-zinc-500'

  if (loading) return <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />
  if (!reg) return <Card className="p-5"><p className="text-sm text-zinc-500">No controls data.</p></Card>

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-zinc-200">Proof of Controls</h3>
          <p className="text-[11px] text-zinc-500">Auto-derived risk controls. {reg.summary.strong} strong · {reg.summary.gap} gap · {reg.summary.verified}/{reg.summary.total} verified.</p>
        </div>
        <button
          onClick={async () => { setDl(true); try { await downloadClientControls(companyId) } finally { setDl(false) } }}
          disabled={dl}
          className="inline-flex items-center gap-1.5 text-xs text-zinc-900 bg-zinc-100 hover:bg-white rounded-lg px-3 py-1.5 font-medium disabled:opacity-50 shrink-0"
        >
          {dl ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileDown className="h-3.5 w-3.5" />} Controls packet
        </button>
      </div>
      <div className="space-y-1">
        {reg.controls.map((c) => (
          <div key={c.key} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
            <span className={`text-[10px] font-semibold uppercase w-16 shrink-0 ${tone(c.status)}`}>{c.status}</span>
            <span className="text-sm text-zinc-200 flex-1">{c.label}</span>
            <span className="text-[11px] text-zinc-500 truncate max-w-[40%]">{c.metric ?? '—'}</span>
            {c.verified && <span className="text-[10px] text-emerald-400 shrink-0">verified</span>}
          </div>
        ))}
      </div>
    </Card>
  )
}
