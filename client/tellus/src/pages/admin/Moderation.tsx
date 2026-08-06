import { useEffect, useState } from 'react'
import { Loader2, Sparkles, Star } from 'lucide-react'
import { tellusApi } from '../../api/tellusClient'
import { Button, Chip, Input, Select } from '../../components/ui'
import type { AdminDmThreadSummary, AdminReportItem, DmMessage } from '../../api/types'

const fmtDateTime = (iso: string) => new Date(iso).toLocaleString()

function ReviewsTab() {
  const [moderationStatus, setModerationStatus] = useState('')
  const [reviewState, setReviewState] = useState('')
  const [brandQ, setBrandQ] = useState('')
  const [items, setItems] = useState<AdminReportItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)
  const [pendingStatus, setPendingStatus] = useState<Record<string, string>>({})
  const [busyId, setBusyId] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    const params = new URLSearchParams()
    if (moderationStatus) params.set('moderation_status', moderationStatus)
    if (reviewState) params.set('review_state', reviewState)
    if (brandQ) params.set('q', brandQ)
    try {
      const res = await tellusApi.get<{ items: AdminReportItem[]; total: number }>(`/admin/reports?${params.toString()}`)
      setItems(res.items)
      setTotal(res.total)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [moderationStatus, reviewState, brandQ])

  async function applyModeration(id: string) {
    const next = pendingStatus[id]
    if (!next) return
    if (next === 'removed' && !window.confirm('Remove this review? The reporter will be notified.')) return
    setBusyId(id)
    try {
      await tellusApi.patch(`/admin/reports/${id}/moderation`, { moderation_status: next })
      await load()
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-end gap-3 border-b border-tu-border px-4 py-3">
        <div className="w-44">
          <Select
            value={moderationStatus}
            onChange={(e) => setModerationStatus(e.target.value)}
            options={[
              { value: '', label: 'All moderation states' }, { value: 'visible', label: 'Visible' },
              { value: 'flagged', label: 'Flagged' }, { value: 'removed', label: 'Removed' },
            ]}
          />
        </div>
        <div className="w-44">
          <Select
            value={reviewState}
            onChange={(e) => setReviewState(e.target.value)}
            options={[
              { value: '', label: 'Any review state' }, { value: 'published', label: 'Published' },
              { value: 'held', label: 'Held' }, { value: 'withdrawn', label: 'Withdrawn' },
            ]}
          />
        </div>
        <div className="w-56">
          <Input placeholder="Search title/description…" value={brandQ} onChange={(e) => setBrandQ(e.target.value)} />
        </div>
        <span className="ml-auto pb-2 text-xs text-tu-faint">{total} results</span>
      </div>

      <div>
        {loading && items.length === 0 && <Loader2 className="m-4 h-5 w-5 animate-spin text-tu-faint" />}
        {items.map((r) => {
          const open = openId === r.id
          return (
            <div key={r.id} className="border-b border-tu-border/70">
              <button
                type="button"
                onClick={() => setOpenId(open ? null : r.id)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-tu-panel2/60"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-tu-text">{r.title || '(no title)'}</span>
                    <Chip>{r.moderation_status}</Chip>
                    {r.review_state && <Chip tone={r.review_state === 'published' ? 'positive' : undefined}>{r.review_state}</Chip>}
                  </div>
                  <div className="mt-0.5 text-xs text-tu-faint">{r.brand_name} · {fmtDateTime(r.created_at)}</div>
                </div>
                {r.rating != null && (
                  <div className="flex shrink-0 items-center gap-0.5 text-tu-accent">
                    <Star className="h-3.5 w-3.5 fill-current" /> <span className="text-xs">{r.rating}</span>
                  </div>
                )}
              </button>
              {open && (
                <div className="px-4 pb-4 pl-8">
                  <p className="text-sm text-tu-dim">{r.description}</p>
                  {r.media.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {r.media.map((m) => (
                        <a key={m.id} href={m.url ?? undefined} target="_blank" rel="noreferrer" className="text-xs text-tu-accent hover:underline">
                          {m.media_type} attachment
                        </a>
                      ))}
                    </div>
                  )}
                  <div className="mt-3 flex items-end gap-2">
                    <div className="w-40">
                      <Select
                        value={pendingStatus[r.id] ?? r.moderation_status}
                        onChange={(e) => setPendingStatus((p) => ({ ...p, [r.id]: e.target.value }))}
                        options={[{ value: 'visible', label: 'Visible' }, { value: 'flagged', label: 'Flagged' }, { value: 'removed', label: 'Removed' }]}
                      />
                    </div>
                    <Button size="sm" variant="soft" loading={busyId === r.id} onClick={() => void applyModeration(r.id)}>Apply</Button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
        {!loading && items.length === 0 && <p className="px-4 py-8 text-center text-sm text-tu-faint">No reviews match these filters.</p>}
      </div>
    </div>
  )
}

function DmsTab() {
  const [items, setItems] = useState<AdminDmThreadSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [openId, setOpenId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Record<string, DmMessage[]>>({})
  const [busyId, setBusyId] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    try {
      const res = await tellusApi.get<{ items: AdminDmThreadSummary[] }>('/admin/dm-threads')
      setItems(res.items)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  async function toggleOpen(t: AdminDmThreadSummary) {
    if (openId === t.id) { setOpenId(null); return }
    setOpenId(t.id)
    if (!messages[t.id]) {
      const rows = await tellusApi.get<DmMessage[]>(`/admin/dm-threads/${t.id}/messages`)
      setMessages((m) => ({ ...m, [t.id]: rows }))
    }
  }

  async function block(t: AdminDmThreadSummary) {
    if (!window.confirm('Block this conversation? Neither side will be able to send messages.')) return
    setBusyId(t.id)
    try { await tellusApi.post(`/admin/dm-threads/${t.id}/block`); await load() } finally { setBusyId(null) }
  }

  async function unblock(t: AdminDmThreadSummary) {
    if (!window.confirm('Unblock this conversation? This may override a block the consumer set themselves.')) return
    setBusyId(t.id)
    try { await tellusApi.post(`/admin/dm-threads/${t.id}/unblock`); await load() } finally { setBusyId(null) }
  }

  return (
    <div>
      {loading && items.length === 0 && <Loader2 className="m-4 h-5 w-5 animate-spin text-tu-faint" />}
      {items.map((t) => (
        <div key={t.id} className="border-b border-tu-border/70">
          <button
            type="button"
            onClick={() => void toggleOpen(t)}
            className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-tu-panel2/60"
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-tu-text">{t.brand_name} ↔ {t.consumer_email}</span>
                {t.blocked && <Chip tone="negative">blocked</Chip>}
              </div>
              <div className="mt-0.5 text-xs text-tu-faint">
                {t.message_count} messages{t.last_message_at ? ` · last ${fmtDateTime(t.last_message_at)}` : ''}
              </div>
            </div>
            <Button
              size="sm" variant="soft" loading={busyId === t.id}
              onClick={(e) => { e.stopPropagation(); void (t.blocked ? unblock(t) : block(t)) }}
            >
              {t.blocked ? 'Unblock' : 'Block'}
            </Button>
          </button>
          {openId === t.id && (
            <div className="space-y-2 px-4 pb-4 pl-8">
              {(messages[t.id] ?? []).map((m) => (
                <div key={m.id} className="text-sm">
                  <span className="font-mono text-xs text-tu-faint">{m.sender_role}</span>{' '}
                  <span className="text-tu-text">{m.body}</span>
                </div>
              ))}
              {(messages[t.id] ?? []).length === 0 && <p className="text-sm text-tu-faint">No messages yet.</p>}
            </div>
          )}
        </div>
      ))}
      {!loading && items.length === 0 && <p className="px-4 py-8 text-center text-sm text-tu-faint">No conversations yet.</p>}
    </div>
  )
}

export default function AdminModeration() {
  const [tab, setTab] = useState<'reviews' | 'dms'>('reviews')

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col overflow-hidden rounded-xl border border-tu-border bg-tu-bg">
      <div className="flex items-center justify-between border-b border-tu-border px-4 py-3">
        <h1 className="flex items-center gap-2 text-sm font-semibold text-tu-text">
          <Sparkles className="h-4 w-4 text-tu-accent" /> Moderation
        </h1>
        <div className="flex gap-1">
          <button
            type="button" onClick={() => setTab('reviews')}
            className={`rounded px-2.5 py-1 text-xs font-medium ${tab === 'reviews' ? 'bg-tu-panel2 text-tu-text' : 'text-tu-faint hover:text-tu-dim'}`}
          >
            Reviews
          </button>
          <button
            type="button" onClick={() => setTab('dms')}
            className={`rounded px-2.5 py-1 text-xs font-medium ${tab === 'dms' ? 'bg-tu-panel2 text-tu-text' : 'text-tu-faint hover:text-tu-dim'}`}
          >
            DMs
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {tab === 'reviews' ? <ReviewsTab /> : <DmsTab />}
      </div>
    </div>
  )
}
