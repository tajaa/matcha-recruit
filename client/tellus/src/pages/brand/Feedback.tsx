import { useCallback, useEffect, useState } from 'react'
import { Award, Frown, ImageIcon, Meh, MessageSquare, Smile, Sparkles, Video } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Chip, Empty, Select, Spinner } from '../../components/ui'
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

function Stat({ label, value, tone = 'text-tu-text', icon: Icon }: { label: string; value: number; tone?: string; icon: typeof MessageSquare }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <Icon className={`h-3.5 w-3.5 ${tone}`} />
      <span className={`font-semibold ${tone}`}>{value}</span>
      <span className="text-tu-faint">{label}</span>
    </span>
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
    <div className="px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Chip tone={report.sentiment}>{report.sentiment}</Chip>
            <Chip>{report.category}</Chip>
            {report.reward_status === 'pending' && <Chip tone="negative">reward pending</Chip>}
            {report.reward_status === 'approved' && report.points_awarded > 0 && (
              <Chip tone="positive">+{report.points_awarded} pts</Chip>
            )}
            {report.reward_status === 'rejected' && <Chip>declined</Chip>}
            {report.store_name && <span className="text-xs text-tu-faint">{report.store_name}</span>}
          </div>
          {report.title && <h3 className="mt-1 text-sm font-semibold">{report.title}</h3>}
        </div>
        <span className="whitespace-nowrap text-xs text-tu-faint">{new Date(report.created_at).toLocaleDateString()}</span>
      </div>

      <p className="mt-1.5 whitespace-pre-wrap text-sm text-tu-dim">{report.description}</p>

      {report.media.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {report.media.map((m) => (
            <a key={m.id} href={m.url ?? '#'} target="_blank" rel="noreferrer"
              className="flex items-center gap-1 rounded-md border border-tu-border px-2 py-1 text-xs text-tu-dim hover:border-tu-accent">
              {m.media_type === 'video' ? <Video className="h-3.5 w-3.5" /> : <ImageIcon className="h-3.5 w-3.5" />}
              {m.media_type}
            </a>
          ))}
        </div>
      )}

      {report.reward_status === 'pending' && (
        <div className="mt-2.5 flex items-center gap-2.5 rounded-md bg-tu-accent/5 px-2.5 py-1.5">
          <Award className="h-3.5 w-3.5 shrink-0 text-tu-accent" />
          <span className="flex-1 text-sm text-tu-dim">Award points for this feedback?</span>
          <Button size="sm" loading={busy} onClick={() => decideReward(true)}>Approve</Button>
          <Button size="sm" variant="danger" loading={busy} onClick={() => decideReward(false)}>Decline</Button>
        </div>
      )}

      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <div className="w-32">
          <Select value={report.status} onChange={(e) => setStatus(e.target.value)} options={STATUS_SET} />
        </div>
        {granting ? (
          <div className="flex items-center gap-2">
            <input type="number" min={1} max={5000} value={grantPts} onChange={(e) => setGrantPts(Number(e.target.value))}
              className="w-14 rounded-md border border-tu-border bg-tu-panel2 px-2 py-1 text-xs" />
            <Button size="sm" loading={busy} onClick={grant}>Grant</Button>
            <Button size="sm" variant="ghost" onClick={() => setGranting(false)}>Cancel</Button>
          </div>
        ) : (
          <Button size="sm" variant="ghost" onClick={() => setGranting(true)}><Award className="h-3.5 w-3.5" /> Grant points</Button>
        )}
        <Button size="sm" variant="ghost" onClick={moderate} className="ml-auto text-tu-bad">Remove</Button>
      </div>
    </div>
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
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Feedback</h1>
        <p className="mt-0.5 text-sm text-tu-dim">Track sentiment across your stores and decide what earns points.</p>
      </div>

      {stats && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 border-b border-tu-border pb-4">
          <Stat label="Total" value={stats.total} icon={MessageSquare} />
          <Stat label="New" value={stats.new} tone="text-tu-accent" icon={Sparkles} />
          <Stat label="Positive" value={stats.positive} tone="text-tu-good" icon={Smile} />
          <Stat label="Neutral" value={stats.neutral} icon={Meh} />
          <Stat label="Negative" value={stats.negative} tone="text-tu-bad" icon={Frown} />
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <div className="w-40"><Select value={status} onChange={(e) => setStatus(e.target.value)} options={STATUS_OPTS} /></div>
        <div className="w-40"><Select value={sentiment} onChange={(e) => setSentiment(e.target.value)} options={SENTIMENT_OPTS} /></div>
      </div>

      {loading ? <Spinner /> : reports.length === 0 ? (
        <Empty>No feedback yet. Share a QR link to start collecting.</Empty>
      ) : (
        <div className="divide-y divide-tu-border rounded-lg border border-tu-border">
          {reports.map((r) => <ReportRow key={r.id} report={r} onChange={load} />)}
        </div>
      )}
    </div>
  )
}
