import { useEffect, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { MessageCircle } from 'lucide-react'
import { tellusApi } from '../api/tellusClient'
import { useAccount } from '../hooks/useAccount'
import { Card, Chip, Empty, ErrorText, Spinner } from '../components/ui'
import { DmThreadPanel } from '../components/DmThreadPanel'
import type { Brand, DmThread, InboxBrand, TellusNotification } from '../api/types'

function hoursLeft(publishAt: string): number {
  return Math.max(0, Math.ceil((Date.parse(publishAt) - Date.now()) / 3_600_000))
}

function StateChip({ t }: { t: DmThread }) {
  if (t.kind === 'general') return <Chip tone={t.status === 'closed' ? undefined : 'positive'}>{t.status === 'closed' ? 'closed' : (t.topic ?? 'question')}</Chip>
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
  const [params] = useSearchParams()
  const location = useLocation()
  const inboxView = location.pathname === '/brand/messages'
  const [kind, setKind] = useState('')
  const [threadStatus, setThreadStatus] = useState('')
  const [inboxBrands, setInboxBrands] = useState<InboxBrand[]>([])
  const [selectedBrandId, setSelectedBrandId] = useState('')
  const [inboxReady, setInboxReady] = useState(!inboxView || account?.account_type === 'brand')
  const [threads, setThreads] = useState<DmThread[]>([])
  const [openId, setOpenId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [messagingEnabled, setMessagingEnabled] = useState<boolean | null>(null)
  const [toggleBusy, setToggleBusy] = useState(false)

  useEffect(() => {
    if (!inboxView || account?.account_type === 'brand') { setInboxReady(true); return }
    setInboxReady(false)
    tellusApi.get<InboxBrand[]>('/comms/inbox-brands')
      .then((rows) => { const active = rows.filter(row => row.plan_status === 'active'); setInboxBrands(active); setSelectedBrandId((current) => current || (active.length === 1 ? active[0].brand_id : '')); setInboxReady(true) })
      .catch((e) => { setErr(e instanceof Error ? e.message : 'Failed to load inboxes'); setInboxReady(true) })
  }, [inboxView, account?.id, account?.account_type])

  useEffect(() => {
    if (!inboxView || account?.account_type !== 'brand') return
    tellusApi.get<Brand>('/brand').then(brand => setMessagingEnabled(brand.messaging_enabled ?? false)).catch(() => {})
  }, [inboxView, account?.id, account?.account_type])

  async function toggleMessaging(enabled: boolean) {
    setToggleBusy(true); setErr('')
    try { await tellusApi.patch('/comms/brand/messaging', { enabled }); setMessagingEnabled(enabled) }
    catch (e) { setErr(e instanceof Error ? e.message : 'Could not update Comms') }
    finally { setToggleBusy(false) }
  }

  useEffect(() => {
    if (!inboxReady || (inboxView && account?.account_type !== 'brand' && !selectedBrandId)) {
      if (inboxReady) setLoading(false)
      return
    }
    const query = new URLSearchParams()
    if (inboxView && kind) query.set('kind', kind)
    if (inboxView && threadStatus) query.set('status', threadStatus)
    if (inboxView && selectedBrandId) query.set('brand_id', selectedBrandId)
    let stopped = false
    async function load() {
      try {
        const rows = await tellusApi.get<DmThread[]>(`/comms/threads${query.toString() ? `?${query}` : ''}`)
        if (stopped) return
        setThreads(rows)
        const wanted = params.get('thread')
        if (wanted && rows.some(t => t.id === wanted)) setOpenId(wanted)
      } catch (e) { if (!stopped) setErr(e instanceof Error ? e.message : 'Failed to load messages') }
      finally { if (!stopped) setLoading(false) }
    }
    void load()
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void load() }, 15_000)
    return () => { stopped = true; window.clearInterval(timer) }
  }, [params, inboxView, kind, threadStatus, selectedBrandId, inboxReady, account?.account_type])

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
      const relevant = notes.filter((n) => (n.kind === 'dm_message' || n.kind === 'dm_assignment') && n.reference_id === id)
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
        <h1 className="text-lg font-semibold">Comms</h1>
        <p className="mt-0.5 text-sm text-tu-dim">
          {account?.account_type === 'brand' ? 'Comms with people who have questions about your business.' : 'Comms with businesses and responses to your feedback.'}
        </p>
      </div>

      {inboxView && <div className="flex flex-wrap gap-2"><select value={kind} onChange={e => setKind(e.target.value)} className="rounded-lg border border-tu-border bg-tu-panel2 px-2 py-1.5 text-xs"><option value="">All conversation types</option><option value="general">Customer questions</option><option value="feedback">Feedback DMs</option></select><select value={threadStatus} onChange={e => setThreadStatus(e.target.value)} className="rounded-lg border border-tu-border bg-tu-panel2 px-2 py-1.5 text-xs"><option value="">All statuses</option><option value="waiting_brand">Needs reply</option><option value="waiting_consumer">Awaiting customer</option><option value="closed">Closed</option></select></div>}

      {inboxView && account?.account_type !== 'brand' && inboxBrands.length > 1 && <select value={selectedBrandId} onChange={e => { setSelectedBrandId(e.target.value); setOpenId(null) }} className="w-full rounded-lg border border-tu-border bg-tu-panel2 px-2 py-1.5 text-xs"><option value="">Choose a business inbox…</option>{inboxBrands.map(b => <option key={b.brand_id} value={b.brand_id}>{b.name}</option>)}</select>}
      {inboxView && account?.account_type === 'brand' && messagingEnabled !== null && <label className="flex items-center gap-2 text-xs text-tu-dim"><input type="checkbox" checked={messagingEnabled} disabled={toggleBusy} onChange={e => void toggleMessaging(e.target.checked)} /> Accept new Comms questions on the public business page</label>}

      {threads.length === 0 ? (
        <Empty>No conversations yet.</Empty>
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
                  {t.kind === 'general' && <p className="mt-0.5 text-xs text-tu-faint">{t.topic ?? 'Question'}{t.store_name ? ` · ${t.store_name}` : ''}{t.store_city ? ` · ${t.store_city}` : ''}</p>}
                  {(t.report_title || t.report_number) && (
                    <p className="mt-0.5 text-xs text-tu-faint">{t.report_title ?? t.report_number}</p>
                  )}
                </div>
                <MessageCircle className="h-4 w-4 shrink-0 text-tu-faint" />
              </button>
              {openId === t.id && (
                <div className="mt-2.5"><DmThreadPanel initialThread={t} isBrand={t.viewer_role === 'brand' || account?.account_type === 'brand'} /></div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
