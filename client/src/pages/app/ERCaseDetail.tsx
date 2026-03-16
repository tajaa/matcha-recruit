import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, Card, Select, type BadgeVariant } from '../../components/ui'
import { NoteThread } from '../../components/NoteThread'
import { ERDocumentList } from '../../components/er/ERDocumentList'
import { ERGuidancePanel } from '../../components/er/ERGuidancePanel'
import { ERTimelinePanel } from '../../components/er/ERTimelinePanel'
import { useERCase } from '../../hooks/er/useERCase'
import {
  categoryLabel,
  statusLabel,
  outcomeLabel,
  NOTE_TYPES,
  type ERCaseStatus,
  type SuggestedGuidanceResponse,
  type TimelineAnalysisResponse,
} from '../../types/er'

const statusVariant: Record<string, BadgeVariant> = {
  open: 'warning',
  in_review: 'neutral',
  pending_determination: 'warning',
  closed: 'success',
}

const STATUS_OPTIONS = [
  { value: 'open', label: 'Open' },
  { value: 'in_review', label: 'In Review' },
  { value: 'pending_determination', label: 'Pending Determination' },
  { value: 'closed', label: 'Closed' },
]

const NOTE_TYPE_CONFIG = NOTE_TYPES.map((t) => ({
  value: t.value,
  label: t.label,
  variant: (t.value === 'guidance' ? 'success' : t.value === 'question' ? 'warning' : 'neutral') as BadgeVariant,
}))

type Tab = 'notes' | 'documents' | 'guidance' | 'timeline'

export default function ERCaseDetail() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const { case_, loading, error, updateCase, deleteCase, refetch } = useERCase(caseId!)
  const [tab, setTab] = useState<Tab>('notes')
  const [guidance, setGuidance] = useState<SuggestedGuidanceResponse | null>(null)
  const [timeline, setTimeline] = useState<TimelineAnalysisResponse | null>(null)

  // Auto-open Documents tab for brand-new cases (0 docs, created <60s ago)
  const [defaultTabSet, setDefaultTabSet] = useState(false)
  useEffect(() => {
    if (case_ && !defaultTabSet) {
      setDefaultTabSet(true)
      const isNew = case_.document_count === 0 &&
        (Date.now() - new Date(case_.created_at).getTime()) < 60_000
      if (isNew) setTab('documents')
    }
  }, [case_, defaultTabSet])

  if (loading) return <p className="text-sm text-zinc-500">Loading case...</p>
  if (error) return <p className="text-sm text-red-400">{error}</p>
  if (!case_) return <p className="text-sm text-zinc-500">Case not found.</p>

  async function handleStatusChange(status: ERCaseStatus) {
    await updateCase({ status })
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Link to="/app/er-copilot" className="text-zinc-500 hover:text-zinc-300 transition-colors">
          &larr;
        </Link>
        <span className="text-xs text-zinc-500 font-mono">{case_.case_number}</span>
        <h1 className="text-xl font-semibold text-zinc-100 font-[Space_Grotesk]">
          {case_.title}
        </h1>
        <Badge variant={statusVariant[case_.status] ?? 'neutral'}>
          {statusLabel[case_.status] ?? case_.status}
        </Badge>
        <Badge variant="neutral">
          {categoryLabel[case_.category ?? ''] ?? case_.category ?? '—'}
        </Badge>
      </div>

      {/* Layout: 2/3 main + 1/3 sidebar */}
      <div className="grid grid-cols-3 gap-6">
        {/* Main column */}
        <div className="col-span-2">
          {/* Tabs */}
          <div className="flex gap-1 mb-4">
            {(['notes', 'documents', 'guidance', 'timeline'] as const).map((t) => (
              <Button
                key={t}
                variant={tab === t ? 'primary' : 'ghost'}
                size="sm"
                onClick={() => setTab(t)}
              >
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </Button>
            ))}
          </div>

          <Card className="p-5">
            {tab === 'notes' && (
              <NoteThread
                endpoint={`/er/cases/${caseId}/notes`}
                noteTypes={NOTE_TYPE_CONFIG}
              />
            )}
            {tab === 'documents' && (
              <ERDocumentList caseId={caseId!} onUploadComplete={refetch} />
            )}
            {tab === 'guidance' && (
              <ERGuidancePanel caseId={caseId!} guidance={guidance} onGuidanceChange={setGuidance} />
            )}
            {tab === 'timeline' && (
              <ERTimelinePanel caseId={caseId!} timeline={timeline} onTimelineChange={setTimeline} />
            )}
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Status & Classification */}
          <Card className="p-0 overflow-hidden">
            <div className="px-5 py-3 border-b border-zinc-800/60 bg-zinc-900/40">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Case Details</h3>
            </div>
            <div className="px-5 py-4 space-y-4">
              <div>
                <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1.5">Status</dt>
                <dd>
                  <Select
                    label=""
                    options={STATUS_OPTIONS}
                    value={case_.status}
                    onChange={(e) => handleStatusChange(e.target.value as ERCaseStatus)}
                  />
                </dd>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">Category</dt>
                  <dd className="text-sm text-zinc-200">{categoryLabel[case_.category ?? ''] ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">Outcome</dt>
                  <dd className="text-sm text-zinc-200">{case_.outcome ? (outcomeLabel[case_.outcome] ?? case_.outcome) : '—'}</dd>
                </div>
              </div>
            </div>
          </Card>

          {/* Dates & Metadata */}
          <Card className="p-0 overflow-hidden">
            <div className="px-5 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">Created</dt>
                  <dd className="text-sm text-zinc-200">{new Date(case_.created_at).toLocaleDateString()}</dd>
                </div>
                <div>
                  <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500 mb-1">Updated</dt>
                  <dd className="text-sm text-zinc-200">{new Date(case_.updated_at).toLocaleDateString()}</dd>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between">
                <dt className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">Documents</dt>
                <dd className="text-sm font-medium text-zinc-200">{case_.document_count}</dd>
              </div>
            </div>
          </Card>

          {/* Description */}
          {case_.description && (
            <Card className="p-0 overflow-hidden">
              <div className="px-5 py-3 border-b border-zinc-800/60 bg-zinc-900/40">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Description</h3>
              </div>
              <div className="px-5 py-4">
                <p className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">{case_.description}</p>
              </div>
            </Card>
          )}

          {/* Actions */}
          <div className="pt-2">
            <button
              type="button"
              className="text-xs text-zinc-600 hover:text-red-400 transition-colors"
              onClick={async () => {
                if (confirm('Delete this case? This cannot be undone.')) {
                  await deleteCase()
                  navigate('/app/er-copilot')
                }
              }}
            >
              Delete case
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
