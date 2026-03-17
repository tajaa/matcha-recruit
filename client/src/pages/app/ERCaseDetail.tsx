import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, Card, Select, type BadgeVariant } from '../../components/ui'
import { NoteThread } from '../../components/NoteThread'
import { ERDocumentList } from '../../components/er/ERDocumentList'
import { ERGuidancePanel } from '../../components/er/ERGuidancePanel'
import { ERTimelinePanel } from '../../components/er/ERTimelinePanel'
import { ERPolicyCheckPanel } from '../../components/er/ERPolicyCheckPanel'
import { ERDiscrepanciesPanel } from '../../components/er/ERDiscrepanciesPanel'
import { ERSimilarCasesPanel } from '../../components/er/ERSimilarCasesPanel'
import { EREvidenceSearch } from '../../components/er/EREvidenceSearch'
import { EROutcomePanel } from '../../components/er/EROutcomePanel'
import { useERCase } from '../../hooks/er/useERCase'
import {
  categoryLabel,
  statusLabel,
  outcomeLabel,
  NOTE_TYPES,
  type ERCaseStatus,
  type ERCaseOutcome,
  type SuggestedGuidanceResponse,
  type TimelineAnalysisResponse,
  type ShareLink,
} from '../../types/er'
import { api } from '../../api/client'

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
  variant: (t.value === 'guidance' ? 'success' : t.value === 'system' ? 'warning' : t.value === 'question' ? 'warning' : 'neutral') as BadgeVariant,
}))

type Tab = 'notes' | 'documents' | 'guidance' | 'discrepancies' | 'similar' | 'evidence' | 'outcome' | 'policy' | 'timeline'

const TAB_LABELS: Record<Tab, string> = {
  notes: 'Notes',
  documents: 'Documents',
  guidance: 'Guidance',
  discrepancies: 'Discrepancies',
  similar: 'Similar Cases',
  evidence: 'Evidence',
  outcome: 'Outcome',
  policy: 'Policy Check',
  timeline: 'Timeline',
}

const ALL_TABS: Tab[] = ['notes', 'documents', 'guidance', 'discrepancies', 'similar', 'evidence', 'outcome', 'policy', 'timeline']

const EXPIRY_OPTIONS = [
  { value: '7', label: '7 days' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
  { value: '', label: 'No expiry' },
]

export default function ERCaseDetail() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const { case_, loading, error, updateCase, deleteCase, refetch } = useERCase(caseId!)
  const [tab, setTab] = useState<Tab>('guidance')
  const [guidance, setGuidance] = useState<SuggestedGuidanceResponse | null>(null)
  const [timeline, setTimeline] = useState<TimelineAnalysisResponse | null>(null)
  const [skipGuidanceCache, setSkipGuidanceCache] = useState(false)

  // Export sidebar state
  const [exportOpen, setExportOpen] = useState(false)
  const [exportPassword, setExportPassword] = useState('')
  const [sharePassword, setSharePassword] = useState('')
  const [shareExpiry, setShareExpiry] = useState('7')
  const [shareLinks, setShareLinks] = useState<ShareLink[]>([])
  const [exporting, setExporting] = useState(false)
  const [creatingLink, setCreatingLink] = useState(false)
  const [newShareUrl, setNewShareUrl] = useState('')

  async function loadShareLinks() {
    try {
      const res = await api.get<{ links: ShareLink[] }>(`/er/cases/${caseId}/export/links`)
      setShareLinks(res.links ?? [])
    } catch { /* no links */ }
  }

  async function handleDownloadPdf() {
    if (!exportPassword.trim()) return
    setExporting(true)
    try {
      const BASE = import.meta.env.VITE_API_URL ?? '/api'
      const token = localStorage.getItem('matcha_access_token')
      const res = await fetch(`${BASE}/er/cases/${caseId}/export`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ password: exportPassword }),
      })
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${case_?.case_number ?? 'case'}-export.pdf`
      a.click()
      URL.revokeObjectURL(url)
      setExportPassword('')
    } catch { /* error handled silently */ } finally {
      setExporting(false)
    }
  }

  async function handleCreateShareLink() {
    if (!sharePassword.trim()) return
    setCreatingLink(true)
    setNewShareUrl('')
    try {
      const body: Record<string, unknown> = { password: sharePassword }
      if (shareExpiry) body.expires_in_days = Number(shareExpiry)
      const res = await api.post<{ url: string }>(`/er/cases/${caseId}/export/share`, body)
      setNewShareUrl(window.location.origin + res.url)
      setSharePassword('')
      loadShareLinks()
    } catch { /* error */ } finally {
      setCreatingLink(false)
    }
  }

  async function handleRevokeLink(linkId: string) {
    try {
      await api.delete(`/er/cases/${caseId}/export/links/${linkId}`)
      loadShareLinks()
    } catch { /* error */ }
  }

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

  async function handleGuidanceGenerated(g: SuggestedGuidanceResponse) {
    setGuidance(g)
    const lines = [g.summary]
    g.cards.forEach((card, i) => {
      lines.push(`${i + 1}. ${card.title}: ${card.recommendation}`)
    })
    try {
      await api.post(`/er/cases/${caseId}/notes`, {
        note_type: 'guidance',
        content: lines.join('\n'),
        metadata: { source: 'auto_guidance', note_purpose: 'next_steps' },
      })
    } catch { /* note is supplementary */ }
  }

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
          <div className="flex gap-1 mb-4 overflow-x-auto">
            {ALL_TABS.map((t) => (
              <Button
                key={t}
                variant={tab === t ? 'primary' : 'ghost'}
                size="sm"
                className="whitespace-nowrap"
                onClick={() => setTab(t)}
              >
                {TAB_LABELS[t]}
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
              <ERDocumentList caseId={caseId!} onUploadComplete={() => { refetch(); setGuidance(null); setTimeline(null); setSkipGuidanceCache(true) }} />
            )}
            {tab === 'guidance' && (
              <ERGuidancePanel
                caseId={caseId!}
                guidance={guidance}
                onGuidanceChange={setGuidance}
                onGuidanceGenerated={handleGuidanceGenerated}
                documentCount={case_.document_count}
                hasDescription={!!case_.description}
                caseStatus={case_.status}
                skipCache={skipGuidanceCache}
                onCacheSkipped={() => setSkipGuidanceCache(false)}
                onBeginDetermination={async (outcome: ERCaseOutcome, adminNotes: string) => {
                  await updateCase({ status: 'closed' as ERCaseStatus, outcome })
                  try {
                    const noteLines = [`Case closed with outcome: ${outcomeLabel[outcome] ?? outcome}`]
                    if (adminNotes.trim()) noteLines.push(`\nAdmin notes: ${adminNotes.trim()}`)
                    await api.post(`/er/cases/${caseId}/notes`, {
                      note_type: 'system',
                      content: noteLines.join(''),
                      metadata: { source: 'determination', note_purpose: 'determination' },
                    })
                  } catch { /* note is supplementary */ }
                }}
              />
            )}
            {tab === 'discrepancies' && (
              <ERDiscrepanciesPanel caseId={caseId!} />
            )}
            {tab === 'similar' && (
              <ERSimilarCasesPanel caseId={caseId!} />
            )}
            {tab === 'evidence' && (
              <EREvidenceSearch caseId={caseId!} />
            )}
            {tab === 'outcome' && (
              <EROutcomePanel caseId={caseId!} onApplyOutcome={async () => { await refetch() }} />
            )}
            {tab === 'policy' && (
              <ERPolicyCheckPanel caseId={caseId!} />
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

          {/* Export Case */}
          <Card className="p-0 overflow-hidden">
            <button
              type="button"
              className="w-full px-5 py-3 flex items-center justify-between border-b border-zinc-800/60 bg-zinc-900/40 hover:bg-zinc-900/60 transition-colors"
              onClick={() => { setExportOpen(!exportOpen); if (!exportOpen) loadShareLinks() }}
            >
              <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">Export Case</h3>
              <span className="text-zinc-500 text-xs">{exportOpen ? '▾' : '▸'}</span>
            </button>
            {exportOpen && (
              <div className="px-5 py-4 space-y-4">
                {/* Direct download */}
                <div className="space-y-2">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">Download PDF</p>
                  <input
                    type="password"
                    value={exportPassword}
                    onChange={(e) => setExportPassword(e.target.value)}
                    placeholder="Password"
                    className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
                  />
                  <Button size="sm" disabled={exporting || !exportPassword.trim()} onClick={handleDownloadPdf}>
                    {exporting ? 'Downloading...' : 'Download PDF'}
                  </Button>
                </div>

                <div className="border-t border-zinc-800" />

                {/* Share link */}
                <div className="space-y-2">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">Create Share Link</p>
                  <input
                    type="password"
                    value={sharePassword}
                    onChange={(e) => setSharePassword(e.target.value)}
                    placeholder="Password"
                    className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
                  />
                  <select
                    value={shareExpiry}
                    onChange={(e) => setShareExpiry(e.target.value)}
                    className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-zinc-300 focus:outline-none focus:border-zinc-500"
                  >
                    {EXPIRY_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <Button size="sm" disabled={creatingLink || !sharePassword.trim()} onClick={handleCreateShareLink}>
                    {creatingLink ? 'Creating...' : 'Create Link'}
                  </Button>
                  {newShareUrl && (
                    <div className="rounded-lg bg-zinc-900 border border-zinc-700 p-2">
                      <p className="text-[11px] text-zinc-500 mb-1">Share URL:</p>
                      <p className="text-xs text-emerald-400 break-all select-all">{newShareUrl}</p>
                    </div>
                  )}
                </div>

                {/* Existing links */}
                {shareLinks.length > 0 && (
                  <>
                    <div className="border-t border-zinc-800" />
                    <div className="space-y-2">
                      <p className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">Active Links</p>
                      {shareLinks.filter((l) => !l.revoked_at).map((link) => (
                        <div key={link.id} className="flex items-center justify-between text-xs border border-zinc-800 rounded-lg px-3 py-2">
                          <div className="min-w-0">
                            <p className="text-zinc-300 truncate">{link.filename}</p>
                            <p className="text-zinc-600">
                              {new Date(link.created_at).toLocaleDateString()} &middot; {link.download_count} downloads
                            </p>
                          </div>
                          <button
                            type="button"
                            className="text-zinc-600 hover:text-red-400 ml-2 shrink-0"
                            onClick={() => handleRevokeLink(link.id)}
                            title="Revoke"
                          >
                            &times;
                          </button>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
          </Card>

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
