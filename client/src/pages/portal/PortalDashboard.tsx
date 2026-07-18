import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { GraduationCap, AlertCircle, CheckCircle2, FileSignature, Loader2, Download } from 'lucide-react'
import { Card, Badge, Button } from '../../components/ui'
import { employeeTrainingApi, type MyTrainingRecord } from '../../api/training/training'
import { portalDocumentsApi, type EmployeeDocument } from '../../api/portal/portalDocuments'
import { formatDateOnly } from '../../utils/dateFormat'

export default function PortalDashboard() {
  const [records, setRecords] = useState<MyTrainingRecord[]>([])
  const [documents, setDocuments] = useState<EmployeeDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Surfaced, not swallowed: a silently-empty document list is indistinguishable
  // from "nothing to sign", and the employee never signs.
  const [docsError, setDocsError] = useState(false)

  useEffect(() => {
    let alive = true
    void (async () => {
      try {
        // Documents are additive to the training list — a portal that can't load
        // them should still render trainings rather than error out entirely.
        const [data, docs] = await Promise.all([
          employeeTrainingApi.myRecords(),
          portalDocumentsApi.list().catch(() => {
            if (alive) setDocsError(true)
            return { documents: [], total: 0 }
          }),
        ])
        if (!alive) return
        setRecords(data)
        setDocuments(docs.documents)
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load')
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  async function downloadCert(rid: string) {
    try {
      const { url } = await employeeTrainingApi.myCertificateUrl(rid)
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

  const pending = records.filter((r) => r.status === 'assigned' || r.status === 'in_progress')
  const completed = records.filter((r) => r.status === 'completed')
  const toSign = documents.filter((d) => d.status === 'pending_signature')

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-semibold text-zinc-100 mb-6">Welcome</h1>

      {docsError && (
        <Card className="p-4 mb-8 text-sm text-amber-400">
          ⚠ We couldn't load your documents. If something is awaiting your signature, it won't show
          here — please reload.
        </Card>
      )}

      {toSign.length > 0 && (
        <>
          <h2 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
            <FileSignature className="w-4 h-4 text-amber-400" /> Awaiting your signature
          </h2>
          <div className="space-y-2 mb-8">
            {toSign.map((d) => (
              <Card key={d.id} className="p-4">
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <div className="text-sm text-zinc-100 font-medium truncate">{d.title}</div>
                    <div className="text-xs text-zinc-500 mt-0.5">
                      Assigned {new Date(d.created_at).toLocaleDateString()}
                      {/* expires_at is a DATE, not a timestamp — parse it as one. */}
                      {d.expires_at && <> · Due {formatDateOnly(d.expires_at)}</>}
                    </div>
                  </div>
                  <Link to={`/portal/documents/${d.id}`}>
                    <Button variant="primary" size="sm">Review &amp; sign</Button>
                  </Link>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}

      <h2 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
        <AlertCircle className="w-4 h-4 text-amber-400" /> To do
      </h2>
      {pending.length === 0 ? (
        <Card className="p-5 text-sm text-zinc-500 mb-8">
          You're all caught up. No pending trainings.
        </Card>
      ) : (
        <div className="space-y-2 mb-8">
          {pending.map((r) => (
            <Card key={r.id} className="p-4">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <GraduationCap className="w-4 h-4 text-emerald-400 shrink-0" />
                    <span className="text-sm text-zinc-100 font-medium">{r.title}</span>
                    {r.required_minutes ? (
                      <Badge variant="neutral">{r.required_minutes} min</Badge>
                    ) : null}
                  </div>
                  <div className="text-xs text-zinc-500">
                    Due {r.due_date || '—'} · Status: {r.status.replace('_', ' ')}
                  </div>
                </div>
                <Link to={`/portal/training/${r.id}`}>
                  <Button variant="primary" size="sm">
                    {r.status === 'in_progress' ? 'Continue' : 'Start'}
                  </Button>
                </Link>
              </div>
            </Card>
          ))}
        </div>
      )}

      <h2 className="text-sm font-semibold text-zinc-300 mb-3 flex items-center gap-2">
        <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Completed
      </h2>
      {completed.length === 0 ? (
        <Card className="p-5 text-sm text-zinc-500">No completed trainings yet.</Card>
      ) : (
        <div className="space-y-2">
          {completed.map((r) => (
            <Card key={r.id} className="p-4">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm text-zinc-100 font-medium">{r.title}</span>
                    {r.score != null && (
                      <Badge variant="success">{r.score.toFixed(1)}%</Badge>
                    )}
                  </div>
                  <div className="text-xs text-zinc-500">
                    Completed {r.completed_date} · Valid until {r.expiration_date || '—'}
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={() => downloadCert(r.id)}>
                  <Download className="w-3 h-3 mr-1" /> Cert
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
