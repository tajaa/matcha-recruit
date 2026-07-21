import { useState, useEffect } from 'react'
import { Download, Loader2, ShieldCheck } from 'lucide-react'
import { Card } from '../../../components/ui'
import {
  fetchClientDefenseIncidents, downloadDefenseIncident,
  type DefenseIncident,
} from '../../../api/broker/broker'

/** Incident defense files the CLIENT has shared with this broker.
 *
 * Not a browsable index of the client's incidents — the backend returns only
 * shared rows, and the PDF download 404s on anything else. The empty state has
 * to explain that, or an empty list reads as "this client has no incidents". */
export function DefenseTab({ companyId }: { companyId: string }) {
  const [incidents, setIncidents] = useState<DefenseIncident[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetchClientDefenseIncidents(companyId)
      .then((r) => setIncidents(r.incidents))
      .catch(() => setIncidents([]))
      .finally(() => setLoading(false))
  }, [companyId])

  if (loading) return <Loader2 className="h-5 w-5 text-zinc-500 animate-spin" />

  return (
    <Card className="p-5">
      <h3 className="text-sm font-medium text-zinc-200 mb-1">Shared incident defense files</h3>
      <p className="text-[11px] text-zinc-500 mb-3">
        Per-incident claims-readiness packets — timeline, witnesses, policy map, corrective actions.
        Your client chooses which incidents to share with you.
      </p>
      {incidents.length === 0 ? (
        <div className="flex items-start gap-2.5 py-2">
          <ShieldCheck className="h-4 w-4 text-zinc-600 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm text-zinc-400">Nothing shared yet.</p>
            <p className="text-xs text-zinc-600 mt-0.5">
              Incident defense files are private to the client. They can share one with you from
              the incident's page in their portal.
            </p>
          </div>
        </div>
      ) : (
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
  )
}
