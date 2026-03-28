import { useEffect, useState } from 'react'
import { Card, Badge, Button } from '../../components/ui'
import { MessageSquareWarning, ExternalLink, X, Check, Eye } from 'lucide-react'
import {
  fetchEscalatedQueries,
  fetchEscalatedQueryDetail,
  resolveEscalatedQuery,
  dismissEscalatedQuery,
  updateEscalatedQueryStatus,
} from '../../api/dashboard'
import type { EscalatedQuery, EscalatedQueryDetail } from '../../types/dashboard'

type StatusTab = 'all' | 'open' | 'in_review' | 'resolved' | 'dismissed'

const SEV_COLORS: Record<string, string> = {
  high: 'bg-red-500',
  medium: 'bg-amber-500',
  low: 'bg-blue-400',
}

const SEV_BADGE: Record<string, 'danger' | 'warning' | 'neutral'> = {
  high: 'danger',
  medium: 'warning',
  low: 'neutral',
}

const STATUS_BADGE: Record<string, 'warning' | 'neutral' | 'success' | 'danger'> = {
  open: 'warning',
  in_review: 'neutral',
  resolved: 'success',
  dismissed: 'danger',
}

function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export default function EscalatedQueries() {
  const [tab, setTab] = useState<StatusTab>('all')
  const [items, setItems] = useState<EscalatedQuery[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<EscalatedQueryDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [resolutionNote, setResolutionNote] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  const loadList = () => {
    setLoading(true)
    const statusParam = tab === 'all' ? undefined : tab
    fetchEscalatedQueries(statusParam)
      .then((res) => {
        setItems(res.items)
        setTotal(res.total)
      })
      .catch(() => {
        setItems([])
        setTotal(0)
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadList()
  }, [tab])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    fetchEscalatedQueryDetail(selectedId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }, [selectedId])

  const handleResolve = async () => {
    if (!selectedId || !resolutionNote.trim()) return
    setActionLoading(true)
    try {
      await resolveEscalatedQuery(selectedId, resolutionNote.trim())
      setSelectedId(null)
      setResolutionNote('')
      loadList()
    } finally {
      setActionLoading(false)
    }
  }

  const handleDismiss = async () => {
    if (!selectedId) return
    setActionLoading(true)
    try {
      await dismissEscalatedQuery(selectedId)
      setSelectedId(null)
      loadList()
    } finally {
      setActionLoading(false)
    }
  }

  const handleMarkInReview = async (id: string) => {
    await updateEscalatedQueryStatus(id, 'in_review')
    loadList()
    if (selectedId === id && detail) {
      setDetail({ ...detail, status: 'in_review' })
    }
  }

  const tabs: { key: StatusTab; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'open', label: 'Open' },
    { key: 'in_review', label: 'In Review' },
    { key: 'resolved', label: 'Resolved' },
    { key: 'dismissed', label: 'Dismissed' },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <MessageSquareWarning className="h-5 w-5 text-amber-500" />
          <h1 className="text-lg font-semibold text-zinc-100">Escalated Queries</h1>
          {total > 0 && (
            <span className="text-xs bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-full">{total}</span>
          )}
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 border-b border-zinc-800/60 pb-px">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => { setTab(t.key); setSelectedId(null) }}
            className={`px-4 py-2 text-xs font-medium transition-colors relative ${
              tab === t.key ? 'text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {t.label}
            {tab === t.key && (
              <span className="absolute bottom-0 left-2 right-2 h-px bg-zinc-300 rounded-full" />
            )}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* List */}
        <div className={`${selectedId ? 'lg:col-span-2' : 'lg:col-span-5'}`}>
          <Card className="p-0">
            {loading ? (
              <div className="px-5 py-8 text-center text-sm text-zinc-500">Loading...</div>
            ) : items.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-zinc-500">
                No escalated queries{tab !== 'all' ? ` with status "${tab.replace('_', ' ')}"` : ''}.
              </div>
            ) : (
              <div className="divide-y divide-zinc-800">
                {items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedId(item.id === selectedId ? null : item.id)}
                    className={`flex items-center gap-3 w-full px-5 py-3 text-left transition-all ${
                      selectedId === item.id
                        ? 'bg-zinc-800/70 border-l-2 border-amber-500'
                        : 'border-l-2 border-transparent hover:bg-zinc-800/40'
                    }`}
                  >
                    <span className={`h-2 w-2 rounded-full shrink-0 ${SEV_COLORS[item.severity] || 'bg-zinc-500'}`} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-zinc-200 truncate">{item.title}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        {item.ai_mode && (
                          <span className="text-[10px] text-zinc-500 bg-zinc-800 px-1.5 py-px rounded">
                            {item.ai_mode}
                          </span>
                        )}
                        {item.ai_confidence != null && (
                          <span className="text-[10px] text-zinc-500">
                            {Math.round(item.ai_confidence * 100)}%
                          </span>
                        )}
                        <span className="text-[10px] text-zinc-600">{timeAgo(item.created_at)}</span>
                      </div>
                    </div>
                    <Badge variant={STATUS_BADGE[item.status] || 'neutral'} className="text-[10px] shrink-0">
                      {item.status.replace('_', ' ')}
                    </Badge>
                  </button>
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Detail panel */}
        {selectedId && (
          <div className="lg:col-span-3">
            <Card className="p-5 space-y-5">
              {detailLoading ? (
                <div className="text-sm text-zinc-500">Loading detail...</div>
              ) : detail ? (
                <>
                  {/* Header row */}
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-sm font-medium text-zinc-100">{detail.title}</h2>
                      {detail.thread_title && (
                        <p className="text-xs text-zinc-500 mt-0.5">Thread: {detail.thread_title}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant={SEV_BADGE[detail.severity] || 'neutral'}>{detail.severity}</Badge>
                      <Badge variant={STATUS_BADGE[detail.status] || 'neutral'}>{detail.status.replace('_', ' ')}</Badge>
                    </div>
                  </div>

                  {/* Confidence bar */}
                  {detail.ai_confidence != null && (
                    <div>
                      <div className="flex items-center justify-between text-xs text-zinc-500 mb-1">
                        <span>AI Confidence</span>
                        <span>{Math.round(detail.ai_confidence * 100)}%</span>
                      </div>
                      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            detail.ai_confidence < 0.4 ? 'bg-red-500' : detail.ai_confidence < 0.65 ? 'bg-amber-500' : 'bg-emerald-500'
                          }`}
                          style={{ width: `${Math.round(detail.ai_confidence * 100)}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* User question */}
                  <div>
                    <p className="text-xs font-medium text-zinc-400 mb-1">User Question</p>
                    <div className="bg-zinc-800/50 rounded-lg px-4 py-3 text-sm text-zinc-200">
                      {detail.user_query}
                    </div>
                  </div>

                  {/* AI reply */}
                  {detail.ai_reply && (
                    <div>
                      <p className="text-xs font-medium text-zinc-400 mb-1">AI Reply</p>
                      <div className="bg-zinc-800/50 rounded-lg px-4 py-3 text-sm text-zinc-300 max-h-48 overflow-y-auto">
                        {detail.ai_reply}
                      </div>
                    </div>
                  )}

                  {/* Missing fields */}
                  {detail.missing_fields && detail.missing_fields.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-zinc-400 mb-1">Missing Fields</p>
                      <div className="flex flex-wrap gap-1">
                        {detail.missing_fields.map((f) => (
                          <span key={f} className="text-xs bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded">
                            {f}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Resolution note (if resolved) */}
                  {detail.resolution_note && (
                    <div>
                      <p className="text-xs font-medium text-zinc-400 mb-1">Resolution</p>
                      <div className="bg-emerald-950/30 border border-emerald-800/30 rounded-lg px-4 py-3 text-sm text-zinc-200">
                        {detail.resolution_note}
                      </div>
                    </div>
                  )}

                  {/* Thread link */}
                  <a
                    href={`/work/${detail.thread_id}`}
                    className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
                  >
                    <ExternalLink className="h-3 w-3" />
                    Open in Matcha Work
                  </a>

                  {/* Actions */}
                  {(detail.status === 'open' || detail.status === 'in_review') && (
                    <div className="border-t border-zinc-800 pt-4 space-y-3">
                      {detail.status === 'open' && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => handleMarkInReview(detail.id)}
                        >
                          <Eye className="h-3.5 w-3.5" /> Mark In Review
                        </Button>
                      )}
                      <div>
                        <textarea
                          value={resolutionNote}
                          onChange={(e) => setResolutionNote(e.target.value)}
                          placeholder="Resolution note..."
                          className="w-full bg-zinc-800/60 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 resize-none"
                          rows={3}
                        />
                      </div>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          onClick={handleResolve}
                          disabled={actionLoading || !resolutionNote.trim()}
                        >
                          <Check className="h-3.5 w-3.5" /> Resolve
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={handleDismiss}
                          disabled={actionLoading}
                        >
                          <X className="h-3.5 w-3.5" /> Dismiss
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-sm text-zinc-500">Could not load details.</div>
              )}
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}
