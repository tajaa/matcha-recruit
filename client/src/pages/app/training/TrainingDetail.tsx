import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Loader2, ArrowLeft, Download } from 'lucide-react'
import { Badge, Button, Card } from '../../../components/ui'
import {
  trainingApi,
  type TrainingRecord,
  type TrainingRequirement,
} from '../../../api/training/training'

export default function TrainingDetail() {
  const { requirementId } = useParams<{ requirementId: string }>()
  const [requirement, setRequirement] = useState<TrainingRequirement | null>(null)
  const [records, setRecords] = useState<TrainingRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!requirementId) return
    let alive = true
    void (async () => {
      setLoading(true)
      setError(null)
      try {
        const [req, recs] = await Promise.all([
          trainingApi.getRequirement(requirementId),
          trainingApi.listRecords(),
        ])
        if (!alive) return
        setRequirement(req)
        setRecords(recs.filter((r) => r.requirement_id === requirementId))
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load training')
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [requirementId])

  async function downloadCert(recordId: string) {
    try {
      const { url } = await trainingApi.certificateUrl(recordId)
      window.open(url, '_blank', 'noopener')
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to load certificate')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading…
      </div>
    )
  }

  if (error) return <p className="text-sm text-red-400">{error}</p>
  if (!requirement) return <p className="text-sm text-zinc-500">Not found.</p>

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <Link to="/app/training" className="text-zinc-500 hover:text-zinc-300">
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <h1 className="text-xl font-semibold text-zinc-100">{requirement.title}</h1>
        <Badge variant="neutral">{requirement.jurisdiction || '—'}</Badge>
        <Badge variant="neutral">{requirement.applies_to}</Badge>
      </div>

      <Card className="p-5 mb-4">
        <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">Description</div>
        <p className="text-sm text-zinc-200 whitespace-pre-wrap">
          {requirement.description ||
            'No description set. This requirement is linked to a global lesson template.'}
        </p>
      </Card>

      <h2 className="text-sm font-semibold text-zinc-300 mb-3">Roster</h2>
      <Card className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900/50 text-xs uppercase text-zinc-500">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Employee</th>
              <th className="text-left px-4 py-2 font-medium">Status</th>
              <th className="text-left px-4 py-2 font-medium">Assigned</th>
              <th className="text-left px-4 py-2 font-medium">Due</th>
              <th className="text-left px-4 py-2 font-medium">Completed</th>
              <th className="text-left px-4 py-2 font-medium">Score</th>
              <th className="text-left px-4 py-2 font-medium">Cert</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {records.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-zinc-500 text-xs">
                  No records yet. Click "Assign" on the requirements list.
                </td>
              </tr>
            )}
            {records.map((r) => (
              <tr key={r.id}>
                <td className="px-4 py-2 text-zinc-200">{r.employee_id.slice(0, 8)}…</td>
                <td className="px-4 py-2">
                  <Badge
                    variant={
                      r.status === 'completed'
                        ? 'success'
                        : r.status === 'expired' || r.status === 'waived'
                        ? 'neutral'
                        : 'warning'
                    }
                  >
                    {r.status}
                  </Badge>
                </td>
                <td className="px-4 py-2 text-zinc-400">{r.assigned_date || '—'}</td>
                <td className="px-4 py-2 text-zinc-400">{r.due_date || '—'}</td>
                <td className="px-4 py-2 text-zinc-400">{r.completed_date || '—'}</td>
                <td className="px-4 py-2 text-zinc-400">
                  {r.score != null ? `${r.score.toFixed(1)}%` : '—'}
                </td>
                <td className="px-4 py-2">
                  {r.status === 'completed' && (
                    <Button variant="ghost" size="sm" onClick={() => downloadCert(r.id)}>
                      <Download className="w-3 h-3" />
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
