import { useEffect, useState } from 'react'
import { MessageCircle } from 'lucide-react'
import { tellusApi } from '../api/tellusClient'
import { useAccount } from '../hooks/useAccount'
import { Card, Chip, Empty, ErrorText, Spinner } from '../components/ui'
import { DmThreadPanel } from '../components/DmThreadPanel'
import type { DmThread, TellusNotification } from '../api/types'

function hoursLeft(publishAt: string): number {
  return Math.max(0, Math.ceil((Date.parse(publishAt) - Date.now()) / 3_600_000))
}

function StateChip({ t }: { t: DmThread }) {
  if (t.review_state === 'held' && t.publish_at) return <Chip>publishes in {hoursLeft(t.publish_at)}h</Chip>
  if (t.review_state === 'published') return <Chip tone="positive">public review</Chip>
  if (t.review_state === 'withdrawn') return <Chip>withdrawn</Chip>
  return <Chip>private feedback</Chip>
}

// One page for both roles — GET /dm/threads is already role-aware. DMs cover
// ANY identified feedback (private, held, published, withdrawn), not just
// public reviews — the point is to reach a reporter before a bad experience
// ever surfaces publicly.
export default function Messages() {
  const { account } = useAccount()
  const isBrand = account?.account_type === 'brand'
  const [threads, setThreads] = useState<DmThread[]>([])
  const [openId, setOpenId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  useEffect(() => {
    tellusApi.get<DmThread[]>('/dm/threads')
      .then(setThreads)
      .catch((e) => setErr(e instanceof Error ? e.message : 'Failed to load messages'))
      .finally(() => setLoading(false))
  }, [])

  // Opening a thread here reads its messages (server marks them read), but that
  // doesn't clear the `dm_message` bell notification or this row's stale chip —
  // both were only ever cleared via the bell's own openNotifications() path.
  async function openThread(id: string) {
    const opening = openId !== id
    setOpenId((cur) => (cur === id ? null : id))
    if (!opening) return
    setThreads((ts) => ts.map((t) => (t.id === id ? { ...t, unread_count: 0 } : t)))
    try {
      const notes = await tellusApi.get<TellusNotification[]>('/notifications?unread_only=true&limit=30')
      const relevant = notes.filter((n) => n.kind === 'dm_message' && n.reference_id === id)
      await Promise.all(relevant.map((n) => tellusApi.post(`/notifications/read?notification_id=${n.id}`)))
    } catch {
      // best-effort — bell badge catches up on its next 60s poll
    }
  }

  if (loading) return <Spinner />
  if (err) return <ErrorText>{err}</ErrorText>

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Messages</h1>
        <p className="mt-0.5 text-sm text-tu-dim">
          {isBrand ? 'Direct conversations with reporters.' : 'Direct conversations with brands about your feedback.'}
        </p>
      </div>

      {threads.length === 0 ? (
        <Empty>{isBrand
          ? 'No conversations yet — open one from any identified report in Feedback.'
          : 'No conversations yet — brands can message you about feedback you submit.'}</Empty>
      ) : (
        <div className="space-y-3">
          {threads.map((t) => (
            <Card key={t.id}>
              <button className="flex w-full items-start justify-between gap-3 text-left"
                onClick={() => openThread(t.id)}>
                <div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StateChip t={t} />
                    {t.unread_count > 0 && <Chip tone="positive">{t.unread_count} new</Chip>}
                    {t.blocked && <Chip>ended</Chip>}
                  </div>
                  <h3 className="mt-1 text-sm font-semibold">{t.counterparty_name}</h3>
                  {(t.report_title || t.report_number) && (
                    <p className="mt-0.5 text-xs text-tu-faint">{t.report_title ?? t.report_number}</p>
                  )}
                </div>
                <MessageCircle className="h-4 w-4 shrink-0 text-tu-faint" />
              </button>
              {openId === t.id && (
                <div className="mt-2.5"><DmThreadPanel initialThread={t} isBrand={!!isBrand} /></div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
