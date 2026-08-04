import { useCallback, useEffect, useState } from 'react'
import { Award, ExternalLink, Frown, Heart, ImageIcon, MessageCircle, Meh, MessageSquare, Smile, Sparkles, Star, Video } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { useAccount } from '../../hooks/useAccount'
import { Button, Chip, Empty, Select, Spinner, Textarea } from '../../components/ui'
import { DmThreadPanel } from '../../components/DmThreadPanel'
import type { FeedbackStats, Report } from '../../api/types'

function hoursLeft(publishAt: string): number {
  return Math.max(0, Math.ceil((Date.parse(publishAt) - Date.now()) / 3_600_000))
}

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
  const [replying, setReplying] = useState(false)
  const [replyText, setReplyText] = useState(report.brand_public_reply ?? '')
  const [showDm, setShowDm] = useState(false)

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
  async function toggleHeart() {
    setBusy(true)
    try {
      if (report.hearted_at) await tellusApi.delete(`/feedback/${report.id}/heart`)
      else await tellusApi.post(`/feedback/${report.id}/heart`)
      onChange()
    } finally { setBusy(false) }
  }
  async function saveReply() {
    setBusy(true)
    try { await tellusApi.put(`/feedback/${report.id}/reply`, { body: replyText }); setReplying(false); onChange() }
    catch (e) { alert(e instanceof Error ? e.message : 'Reply failed') } finally { setBusy(false) }
  }
  async function removeReply() {
    if (!confirm('Remove your public reply?')) return
    setBusy(true)
    try { await tellusApi.delete(`/feedback/${report.id}/reply`); onChange() } finally { setBusy(false) }
  }

  return (
    <div className="px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Chip tone={report.sentiment}>{report.sentiment}</Chip>
            <Chip>{report.category}</Chip>
            {report.rating != null && (
              <span className="inline-flex items-center gap-0.5 text-xs text-tu-accent">
                <Star className="h-3 w-3 fill-tu-accent" /> {report.rating}
              </span>
            )}
            {report.review_state === 'held' && report.publish_at && (
              <Chip>publishes in {hoursLeft(report.publish_at)}h</Chip>
            )}
            {report.review_state === 'published' && <Chip tone="positive">public review</Chip>}
            {report.review_state === 'withdrawn' && <Chip>withdrawn</Chip>}
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

      {report.brand_public_reply && !replying && (
        <div className="mt-2.5 rounded-md border border-tu-border bg-tu-panel2 px-2.5 py-1.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-tu-dim">Your public reply</span>
            <div className="flex gap-2">
              {report.review_state !== 'withdrawn' && (
                <button onClick={() => setReplying(true)} className="text-xs text-tu-accent hover:underline">Edit</button>
              )}
              <button onClick={removeReply} className="text-xs text-tu-bad hover:underline">Remove</button>
            </div>
          </div>
          <p className="mt-1 whitespace-pre-wrap text-sm text-tu-text">{report.brand_public_reply}</p>
        </div>
      )}

      {replying && (
        <div className="mt-2.5 space-y-2">
          <Textarea value={replyText} onChange={(e) => setReplyText(e.target.value)} rows={3}
            placeholder="Reply publicly to this review…" />
          <div className="flex gap-2">
            <Button size="sm" loading={busy} onClick={saveReply}>Save reply</Button>
            <Button size="sm" variant="ghost" onClick={() => setReplying(false)}>Cancel</Button>
          </div>
        </div>
      )}

      {showDm && <div className="mt-2.5"><DmThreadPanel reportId={report.id} isBrand /></div>}

      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <div className="w-32">
          <Select value={report.status} onChange={(e) => setStatus(e.target.value)} options={STATUS_SET} />
        </div>
        <Button size="sm" variant="ghost" loading={busy} onClick={toggleHeart}>
          <Heart className={`h-3.5 w-3.5 ${report.hearted_at ? 'fill-tu-accent text-tu-accent' : ''}`} />
          {report.hearted_at ? 'Hearted' : 'Heart'}
        </Button>
        {report.review_state != null && report.review_state !== 'withdrawn' && !report.brand_public_reply && !replying && (
          <Button size="sm" variant="ghost" onClick={() => setReplying(true)}><MessageSquare className="h-3.5 w-3.5" /> Reply publicly</Button>
        )}
        {report.is_identified && (
          <Button size="sm" variant="ghost" onClick={() => setShowDm((s) => !s)}>
            <MessageCircle className="h-3.5 w-3.5" /> {report.has_dm_thread ? 'View conversation' : 'Message reviewer'}
          </Button>
        )}
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
  const { account } = useAccount()
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
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Feedback</h1>
          <p className="mt-0.5 text-sm text-tu-dim">Track sentiment across your stores and decide what earns points.</p>
        </div>
        {account?.brand_slug && (
          <a href={`/tellus/b/${account.brand_slug}`} target="_blank" rel="noreferrer"
            className="flex shrink-0 items-center gap-1 text-xs text-tu-accent hover:underline">
            View public page <ExternalLink className="h-3 w-3" />
          </a>
        )}
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
