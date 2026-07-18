import { useEffect, useState, useCallback, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { handbooks } from '../../../api/client'
import { Button, Badge } from '../../../components/ui'
import { HandbookDistributeModal } from '../../../components/handbook/HandbookDistributeModal'
import type { HandbookListItem } from '../../../types/handbook'
import { WORKBOOK_TYPE_LABELS } from '../../../types/handbook'

type Tab = 'all' | 'active' | 'draft' | 'archived'

const STATUS_BADGE = {
  draft: 'neutral',
  active: 'success',
  archived: 'warning',
} as const

const MODE_LABEL = {
  single_state: 'Single State',
  multi_state: 'Multi-State',
} as const

const SOURCE_LABEL = {
  template: 'Template',
  upload: 'Upload',
} as const

export default function Handbooks() {
  const navigate = useNavigate()
  const [items, setItems] = useState<HandbookListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>('all')
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [distributeId, setDistributeId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  const fetchHandbooks = useCallback(async () => {
    try {
      setItems(await handbooks.list())
    } catch {
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchHandbooks() }, [fetchHandbooks])

  const filtered = tab === 'all' ? items : items.filter((hb) => hb.status === tab)

  const grouped = useMemo(() => {
    const groups: Record<string, HandbookListItem[]> = {}
    for (const hb of filtered) {
      const key = hb.workbook_type || 'general'
      if (!groups[key]) groups[key] = []
      groups[key].push(hb)
    }
    return Object.entries(groups)
      .sort(([a], [b]) =>
        (WORKBOOK_TYPE_LABELS[a as keyof typeof WORKBOOK_TYPE_LABELS] ?? a)
          .localeCompare(WORKBOOK_TYPE_LABELS[b as keyof typeof WORKBOOK_TYPE_LABELS] ?? b),
      )
  }, [filtered])

  const useGrouping = grouped.length > 1

  function toggleGroup(key: string) {
    setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  async function handlePublish(id: string) {
    setActionLoading(id)
    setError(null)
    try {
      await handbooks.publish(id)
      fetchHandbooks()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Publish failed')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleArchive(id: string) {
    if (!window.confirm('Archive this handbook?')) return
    setActionLoading(id)
    setError(null)
    try {
      await handbooks.archive(id)
      fetchHandbooks()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Archive failed')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleDownload(id: string, title: string) {
    try {
      await handbooks.downloadPdf(id, title)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed')
    }
  }

  function renderRow(hb: HandbookListItem) {
    return (
      <div key={hb.id} className="border-t border-white/5 px-5 py-4 hover:bg-white/[0.02] transition-colors">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <Link
                to={`/app/handbook/${hb.id}`}
                className="text-[13px] font-medium text-zinc-100 hover:text-emerald-400 truncate transition-colors"
              >
                {hb.title}
              </Link>
              <Badge variant={STATUS_BADGE[hb.status]}>{hb.status}</Badge>
              {hb.pending_changes_count > 0 && (
                <Badge variant="warning">{hb.pending_changes_count} pending</Badge>
              )}
            </div>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap text-[10px] font-mono uppercase tracking-widest text-zinc-500">
              <span>{MODE_LABEL[hb.mode]}</span>
              <span className="text-zinc-700">\u00b7</span>
              <span>{SOURCE_LABEL[hb.source_type]}</span>
              <span className="text-zinc-700">\u00b7</span>
              <span>v{hb.active_version}</span>
              <span className="text-zinc-700">\u00b7</span>
              <span className="text-zinc-600">
                upd {new Date(hb.updated_at).toLocaleDateString()}
              </span>
              {hb.published_at && (
                <>
                  <span className="text-zinc-700">\u00b7</span>
                  <span className="text-zinc-600">
                    pub {new Date(hb.published_at).toLocaleDateString()}
                  </span>
                </>
              )}
            </div>
            {hb.scope_states.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {hb.scope_states.map((st) => (
                  <span
                    key={st}
                    className="inline-block rounded bg-zinc-950 border border-white/5 px-1.5 py-0.5 text-[10px] font-mono text-zinc-400"
                  >
                    {st}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {hb.status !== 'archived' && (
              <Button size="sm" variant="ghost" onClick={() => navigate(`/app/handbook/${hb.id}/edit`)}>
                Edit
              </Button>
            )}
            {hb.status === 'draft' && (
              <Button size="sm" variant="ghost" onClick={() => handlePublish(hb.id)} disabled={actionLoading === hb.id}>
                Publish
              </Button>
            )}
            {hb.status === 'active' && (
              <Button size="sm" variant="ghost" onClick={() => handleArchive(hb.id)} disabled={actionLoading === hb.id}>
                Archive
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={() => handleDownload(hb.id, hb.title)}>
              Download
            </Button>
            {hb.status === 'active' && (
              <Button size="sm" variant="ghost" onClick={() => setDistributeId(hb.id)} disabled={actionLoading === hb.id}>
                Distribute
              </Button>
            )}
          </div>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <div className="text-xs text-zinc-500 uppercase tracking-widest font-mono animate-pulse">Loading handbooks\u2026</div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-2xl p-3 text-sm text-red-400 flex items-center justify-between">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} className="text-red-500 hover:text-red-300 text-xs">Dismiss</button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100">Handbooks</h1>
          <p className="mt-1 text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
            Create, manage, and distribute employee handbooks
          </p>
        </div>
        <Button onClick={() => navigate('/app/handbook/new')}>Create Handbook</Button>
      </div>

      {/* Tabs \u2014 pill style */}
      <div className="flex gap-0 border border-zinc-700 rounded-xl overflow-hidden w-fit">
        {(['all', 'active', 'draft', 'archived'] as Tab[]).map((t) => {
          const count = t === 'all' ? items.length : items.filter((h) => h.status === t).length
          return (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-5 py-2 text-[11px] uppercase tracking-widest font-bold transition-colors ${
                tab === t
                  ? 'bg-zinc-800 text-zinc-50'
                  : 'bg-zinc-900 text-zinc-500 hover:text-zinc-300'
              }`}
            >
              {t} ({count})
            </button>
          )
        })}
      </div>

      {/* List */}
      {filtered.length === 0 ? (
        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-12 text-center">
          <p className="text-sm text-zinc-400">
            {tab === 'all' ? 'No handbooks yet.' : `No ${tab} handbooks.`}
          </p>
          <p className="text-[11px] text-zinc-600 mt-1">
            {tab === 'all' ? 'Create one to get started.' : 'Switch tab or create a new handbook.'}
          </p>
        </div>
      ) : useGrouping ? (
        <div className="space-y-4">
          {grouped.map(([key, hbs]) => {
            const label = WORKBOOK_TYPE_LABELS[key as keyof typeof WORKBOOK_TYPE_LABELS] ?? key
            const isCollapsed = !!collapsed[key]
            return (
              <div key={key} className="bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden">
                <button
                  type="button"
                  onClick={() => toggleGroup(key)}
                  className="w-full flex items-center justify-between px-5 py-3 bg-zinc-950/50 hover:bg-zinc-950/70 transition-colors"
                >
                  <span className="text-[10px] font-bold text-zinc-400 tracking-widest uppercase">
                    {label} <span className="text-zinc-600 font-mono">({hbs.length})</span>
                  </span>
                  <span className="text-zinc-500 text-xs font-mono">{isCollapsed ? '+' : '\u2212'}</span>
                </button>
                {!isCollapsed && hbs.map(renderRow)}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden">
          {filtered.map(renderRow)}
        </div>
      )}

      {distributeId && (
        <HandbookDistributeModal
          open={!!distributeId}
          onClose={() => setDistributeId(null)}
          handbookId={distributeId}
          onDistributed={fetchHandbooks}
        />
      )}
    </div>
  )
}
