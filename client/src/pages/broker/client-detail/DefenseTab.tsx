import { useState, useEffect } from 'react'
import { Download, Loader2 } from 'lucide-react'
import { Card } from '../../../components/ui'
import {
  fetchClientDefenseIncidents, downloadDefenseIncident,
  fetchClientDefenseErCases, downloadDefenseErCase,
  type DefenseIncident, type DefenseErCase,
} from '../../../api/broker'

export function DefenseTab({ companyId }: { companyId: string }) {
  const [incidents, setIncidents] = useState<DefenseIncident[]>([])
  const [cases, setCases] = useState<DefenseErCase[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.allSettled([
      fetchClientDefenseIncidents(companyId).then((r) => setIncidents(r.incidents)),
      fetchClientDefenseErCases(companyId).then((r) => setCases(r.cases)),
    ]).finally(() => setLoading(false))
  }, [companyId])

  if (loading) return <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />

  return (
    <div className="space-y-4">
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 mb-1">Incident defense files</h3>
        <p className="text-[11px] text-zinc-500 mb-3">Per-incident claims-readiness packets — timeline, witnesses, policy map, corrective actions.</p>
        {incidents.length === 0 ? <p className="text-sm text-zinc-500">No incidents on file.</p> : (
          <div className="space-y-1">
            {incidents.map((i) => (
              <div key={i.id} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
                <span className="text-[11px] text-zinc-500 w-24 shrink-0">{i.incident_number ?? '—'}</span>
                <span className="text-sm text-zinc-200 flex-1 truncate">{i.title ?? 'Incident'}</span>
                <span className="text-[11px] text-zinc-500">{i.severity ?? ''}</span>
                <button onClick={() => downloadDefenseIncident(companyId, i.id, i.incident_number)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-emerald-400 px-2 py-1 rounded-lg border border-zinc-700"><Download className="h-3.5 w-3.5" /> PDF</button>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card className="p-5">
        <h3 className="text-sm font-medium text-zinc-200 mb-1">ER case defense files</h3>
        <p className="text-[11px] text-zinc-500 mb-3">Per-case defense packets — timeline, notes, documents, determination.</p>
        {cases.length === 0 ? <p className="text-sm text-zinc-500">No ER cases on file.</p> : (
          <div className="space-y-1">
            {cases.map((c) => (
              <div key={c.id} className="flex items-center gap-3 py-1.5 border-b border-zinc-800/30 last:border-0">
                <span className="text-[11px] text-zinc-500 w-24 shrink-0">{c.case_number ?? '—'}</span>
                <span className="text-sm text-zinc-200 flex-1 truncate">{c.title ?? 'Case'}</span>
                <span className="text-[11px] text-zinc-500">{c.status ?? ''}</span>
                <button onClick={() => downloadDefenseErCase(companyId, c.id, c.case_number)} className="inline-flex items-center gap-1 text-xs text-zinc-300 hover:text-emerald-400 px-2 py-1 rounded-lg border border-zinc-700"><Download className="h-3.5 w-3.5" /> PDF</button>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
