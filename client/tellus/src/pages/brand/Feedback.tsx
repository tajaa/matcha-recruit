import { useCallback, useEffect, useState } from 'react'
import { Award, ImageIcon, Video } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Card, Chip, Empty, Select, Spinner } from '../../components/ui'
import type { FeedbackStats, Report } from '../../api/types'

const STATUS_OPTS = [
  { value: '', label: 'All statuses' },
  { value: 'new', label: 'New' },
  { value: 'reviewing', label: 'Reviewing' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'archived', label: 'Archived' },
]
const SENTIMENT_OPTS = [
  { value: '', label: 'All sentiment' },
  { value: 'positive', label: 'Positive' },
  { value: 'neutral', label: 'Neutral' },
  { value: 'negative', label: 'Negative' },
]
const STATUS_SET = [
  { value: 'new', label: 'New' },
  { value: 'reviewing', label: 'Reviewing' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'archived', label: 'Archived' },
]

function Stat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <Card className="text-center">
      <p className={`text-2xl font-black ${tone ?? ''}`}>{value}</p>
      <p className="text-xs text-tu-faint">{label}</p>
    </Card>
  )
}

function ReportRow({ report, onChange }: { report: Report; onChange: () => void }) {
  const [granting, setGranting] = useState(false)
  const [grantPts, setGrantPts] = useState(50)
  const [busy, setBusy] = useState(false)

  async function setStatus(status: string) {
    setBusy(true)
    try { await tellusApi.patch(`/feedback/${report.id}/status`, { status }); onChange() } finally { setBusy(false) }
  }
  async function decideReward(approve: boolean) {
    setBusy(true)
    try { await tellusApi.post(`/feedback/${report.id}/reward`, { approve }); onChange() }
    catch (e) { alert(e instanceof Error ? e.message : 'Decision failed') } finally { setBusy(false) }
  }
  async function grant() {
    setBusy(true)
    try { await tellusApi.post('/grants', { report_id: report.id, points: grantPts }); setGranting(false); onChange() }
    catch (e) { alert(e instanceof Error ? e.message : 'Grant failed') } finally { setBusy(false) }
  }
  async function moderate() {
    if (!confirm('Remove this feedback from your dashboard?')) return
    setBusy(true)
    try { await tellusApi.patch(`/feedback/${report.id}/moderation`, { moderation_status: 'removed' }); onChange() } finally { setBusy(false) }
  }

  return (
    <Card className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Chip tone={report.sentiment}>{report.sentiment}</Chip>
            <Chip>{report.category}</Chip>
            {report.reward_status === 'pending' && <Chip tone="negative">reward pending</Chip>}
            {report.reward_status === 'approved' && report.points_awarded > 0 && (
              <Chip tone="positive">+{report.points_awarded} pts</Chip>
            )}
            {report.reward_status === 'rejected' && <Chip>declined</Chip>}
            {report.store_name && <span className="text-xs text-tu-faint">{report.store_name}</span>}
          </div>
          {report.title && <h3 className="mt-2 font-semibold">{report.title}</h3>}
        </div>
        <span className="whitespace-nowrap text-xs text-tu-faint">{new Date(report.created_at).toLocaleDateString()}</span>
      </div>

      <p className="whitespace-pre-wrap text-sm text-tu-dim">{report.description}</p>

      {report.media.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {report.media.map((m) => (
            <a key={m.id} href={m.url ?? '#'} target="_blank" rel="noreferrer"
              className="flex items-center gap-1 rounded-lg border border-tu-border px-2 py-1 text-xs text-tu-dim hover:border-tu-accent">
              {m.media_type === 'video' ? <Video className="h-3.5 w-3.5" /> : <ImageIcon className="h-3.5 w-3.5" />}
              {m.media_type}
            </a>
          ))}
        </div>
      )}

      {report.reward_status === 'pending' && (
        <div className="flex items-center gap-2 rounded-lg border border-tu-accent/30 bg-tu-accent/5 p-3">
          <span className="flex-1 text-sm text-tu-dim">Award points for this feedback?</span>
          <Button loading={busy} onClick={() => decideReward(true)}>Approve</Button>
          <Button variant="danger" loading={busy} onClick={() => decideReward(false)}>Decline</Button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-tu-border pt-3">
        <div className="w-40">
          <Select value={report.status} onChange={(e) => setStatus(e.target.value)} options={STATUS_SET} />
        </div>
        {granting ? (
          <div className="flex items-center gap-2">
            <input type="number" min={1} max={5000} value={grantPts} onChange={(e) => setGrantPts(Number(e.target.value))}
              className="w-20 rounded-lg border border-tu-border bg-tu-panel2 px-2 py-1.5 text-sm" />
            <Button loading={busy} onClick={grant}>Grant</Button>
            <Button variant="ghost" onClick={() => setGranting(false)}>Cancel</Button>
          </div>
        ) : (
          <Button variant="soft" onClick={() => setGranting(true)}><Award className="h-4 w-4" /> Grant points</Button>
        )}
        <Button variant="ghost" onClick={moderate} className="ml-auto text-tu-bad">Remove</Button>
      </div>
    </Card>
  )
}

export default function BrandFeedback() {
  const [stats, setStats] = useState<FeedbackStats | null>(null)
  const [reports, setReports] = useState<Report[]>([])
  const [status, setStatus] = useState('')
  const [sentiment, setSentiment] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (sentiment) params.set('sentiment', sentiment)
    const [s, r] = await Promise.all([
      tellusApi.get<FeedbackStats>('/feedback/stats'),
      tellusApi.get<Report[]>(`/feedback?${params.toString()}`),
    ])
    setStats(s); setReports(r); setLoading(false)
  }, [status, sentiment])

  useEffect(() => { void load() }, [load])

  return (
    <div className="space-y-5">
      <h1 className="text-lg font-bold">Feedback</h1>

      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Stat label="Total" value={stats.total} />
          <Stat label="New" value={stats.new} tone="text-tu-accent" />
          <Stat label="Positive" value={stats.positive} tone="text-tu-good" />
          <Stat label="Neutral" value={stats.neutral} />
          <Stat label="Negative" value={stats.negative} tone="text-tu-bad" />
        </div>
      )}

      <div className="flex gap-3">
        <div className="w-44"><Select value={status} onChange={(e) => setStatus(e.target.value)} options={STATUS_OPTS} /></div>
        <div className="w-44"><Select value={sentiment} onChange={(e) => setSentiment(e.target.value)} options={SENTIMENT_OPTS} /></div>
      </div>

      {loading ? <Spinner /> : reports.length === 0 ? (
        <Empty>No feedback yet. Share a QR link to start collecting.</Empty>
      ) : (
        <div className="space-y-3">
          {reports.map((r) => <ReportRow key={r.id} report={r} onChange={load} />)}
        </div>
      )}
    </div>
  )
}
