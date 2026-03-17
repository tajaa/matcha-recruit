import { useEffect, useState, useCallback } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { handbooks } from '../../api/client'
import { Button, Badge, Card } from '../../components/ui'
import { HandbookSectionSidebar } from '../../components/handbook/HandbookSectionSidebar'
import { HandbookSectionEditor } from '../../components/handbook/HandbookSectionEditor'
import { HandbookChangeRequests } from '../../components/handbook/HandbookChangeRequests'
import { HandbookFreshnessPanel } from '../../components/handbook/HandbookFreshnessPanel'
import { HandbookCoveragePanel } from '../../components/handbook/HandbookCoveragePanel'
import { HandbookDistributeModal } from '../../components/HandbookDistributeModal'
import type {
  HandbookDetail as HandbookDetailType,
  HandbookSection,
  HandbookChangeRequest,
  HandbookAcknowledgementSummary,
  HandbookFreshnessCheck,
  HandbookCoverage,
} from '../../types/handbook'

const STATUS_BADGE = {
  draft: 'neutral',
  active: 'success',
  archived: 'warning',
} as const

export default function HandbookDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [handbook, setHandbook] = useState<HandbookDetailType | null>(null)
  const [changes, setChanges] = useState<HandbookChangeRequest[]>([])
  const [ackSummary, setAckSummary] = useState<HandbookAcknowledgementSummary | null>(null)
  const [freshnessCheck, setFreshnessCheck] = useState<HandbookFreshnessCheck | null>(null)
  const [coverage, setCoverage] = useState<HandbookCoverage | null>(null)
  const [initialLoading, setInitialLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [activeSection, setActiveSection] = useState<HandbookSection | null>(null)
  const [dirtyIds, setDirtyIds] = useState<Set<string>>(new Set())
  const [changeActionLoading, setChangeActionLoading] = useState<string | null>(null)
  const [freshnessRunning, setFreshnessRunning] = useState(false)
  const [showDistribute, setShowDistribute] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)

  const loadData = useCallback(async () => {
    if (!id) return
    try {
      const [hb, ch, ack, fc, cov] = await Promise.all([
        handbooks.get(id),
        handbooks.listChanges(id),
        handbooks.acknowledgements(id).catch(() => null),
        handbooks.getLatestFreshnessCheck(id).catch(() => null),
        handbooks.getCoverage(id).catch(() => null),
      ])
      setHandbook(hb)
      setChanges(ch)
      setAckSummary(ack)
      setFreshnessCheck(fc)
      setCoverage(cov)
      // Preserve active section across reloads, or default to first
      setActiveSection((prev) =>
        prev ? (hb.sections.find((s) => s.id === prev.id) ?? hb.sections[0] ?? null) : (hb.sections[0] ?? null),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load handbook')
    } finally {
      setInitialLoading(false)
    }
  }, [id])

  useEffect(() => { loadData() }, [loadData])

  const handleDirtyChange = useCallback((sectionId: string, dirty: boolean) => {
    setDirtyIds((prev) => {
      const next = new Set(prev)
      if (dirty) next.add(sectionId)
      else next.delete(sectionId)
      return next
    })
  }, [])

  async function handleSaveSection(sectionId: string, content: string) {
    if (!handbook) return
    const section = handbook.sections.find((s) => s.id === sectionId)
    if (!section) return

    const allSections = handbook.sections.map((s) =>
      s.id === sectionId
        ? { section_key: s.section_key, title: s.title, content, section_order: s.section_order, section_type: s.section_type }
        : { section_key: s.section_key, title: s.title, content: s.content, section_order: s.section_order, section_type: s.section_type },
    )
    await handbooks.update(handbook.id, { sections: allSections })
    await loadData()
  }

  async function handleMarkReviewed(sectionId: string) {
    if (!handbook) return
    await handbooks.markSectionReviewed(handbook.id, sectionId)
    await loadData()
  }

  async function handleAcceptChange(changeId: string) {
    if (!handbook) return
    setChangeActionLoading(changeId)
    try {
      await handbooks.acceptChange(handbook.id, changeId)
      await loadData()
    } finally {
      setChangeActionLoading(null)
    }
  }

  async function handleRejectChange(changeId: string) {
    if (!handbook) return
    setChangeActionLoading(changeId)
    try {
      await handbooks.rejectChange(handbook.id, changeId)
      await loadData()
    } finally {
      setChangeActionLoading(null)
    }
  }

  function handleJumpToSection(sectionKey: string) {
    if (!handbook) return
    const section = handbook.sections.find((s) => s.section_key === sectionKey)
    if (section) setActiveSection(section)
  }

  async function handleRunFreshness() {
    if (!handbook) return
    setFreshnessRunning(true)
    try {
      const result = await handbooks.runFreshnessCheck(handbook.id)
      setFreshnessCheck(result)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Freshness check failed')
    } finally {
      setFreshnessRunning(false)
    }
  }

  async function handlePublish() {
    if (!handbook) return
    setActionLoading(true)
    try {
      await handbooks.publish(handbook.id)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Publish failed')
    } finally {
      setActionLoading(false)
    }
  }

  async function handleArchive() {
    if (!handbook || !window.confirm('Archive this handbook? It will no longer be distributed to employees.')) return
    setActionLoading(true)
    try {
      await handbooks.archive(handbook.id)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Archive failed')
    } finally {
      setActionLoading(false)
    }
  }

  async function handleDownload() {
    if (!handbook) return
    try {
      await handbooks.downloadPdf(handbook.id, handbook.title)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed')
    }
  }

  if (initialLoading) return <p className="text-sm text-zinc-500">Loading handbook...</p>
  if (error && !handbook) return <p className="text-sm text-red-400">{error}</p>
  if (!handbook) return <p className="text-sm text-zinc-500">Handbook not found.</p>

  return (
    <div>
      {/* Error banner for non-fatal errors */}
      {error && handbook && (
        <div className="mb-4 p-3 rounded-lg border border-red-800/50 bg-red-900/20 text-sm text-red-400 flex items-center justify-between">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} className="text-red-500 hover:text-red-300 text-xs">Dismiss</button>
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link to="/app/handbooks" className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">
              Handbooks
            </Link>
            <span className="text-xs text-zinc-700">/</span>
          </div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">{handbook.title}</h1>
            <Badge variant={STATUS_BADGE[handbook.status]}>{handbook.status}</Badge>
            <Badge variant="neutral">v{handbook.active_version}</Badge>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {handbook.status !== 'archived' && (
            <Button size="sm" variant="ghost" onClick={() => navigate(`/app/handbook/${handbook.id}/edit`)}>
              Edit
            </Button>
          )}
          {handbook.status === 'draft' && (
            <Button size="sm" onClick={handlePublish} disabled={actionLoading}>
              {actionLoading ? 'Publishing...' : 'Publish'}
            </Button>
          )}
          {handbook.status === 'active' && (
            <>
              <Button size="sm" variant="secondary" onClick={() => setShowDistribute(true)}>
                Distribute
              </Button>
              <Button size="sm" variant="ghost" onClick={handleArchive} disabled={actionLoading}>
                {actionLoading ? 'Archiving...' : 'Archive'}
              </Button>
            </>
          )}
          <Button size="sm" variant="ghost" onClick={handleDownload}>
            Download PDF
          </Button>
        </div>
      </div>

      {/* Acknowledgement Summary */}
      {ackSummary && (
        <Card className="mb-4">
          <h3 className="text-sm font-semibold text-zinc-300 mb-2">Acknowledgements</h3>
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: 'Assigned', value: ackSummary.assigned_count },
              { label: 'Signed', value: ackSummary.signed_count },
              { label: 'Pending', value: ackSummary.pending_count },
              { label: 'Expired', value: ackSummary.expired_count },
            ].map(({ label, value }) => (
              <div key={label} className="text-center">
                <p className="text-lg font-semibold text-zinc-200">{value}</p>
                <p className="text-xs text-zinc-500">{label}</p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Two-column: Sidebar + Editor */}
      <div className="grid grid-cols-[260px_1fr] gap-4 mb-4">
        <div className="border border-zinc-800 rounded-lg p-3 max-h-[600px] overflow-y-auto">
          <HandbookSectionSidebar
            sections={handbook.sections}
            activeId={activeSection?.id ?? null}
            dirtyIds={dirtyIds}
            onSelect={setActiveSection}
          />
        </div>
        <div>
          {activeSection ? (
            <HandbookSectionEditor
              section={activeSection}
              onSave={handleSaveSection}
              onMarkReviewed={handleMarkReviewed}
              onDirtyChange={handleDirtyChange}
            />
          ) : (
            <div className="border border-zinc-800 rounded-lg p-8 text-center">
              <p className="text-sm text-zinc-600">Select a section from the sidebar to edit.</p>
            </div>
          )}
        </div>
      </div>

      {/* Change Requests */}
      <div className="mb-4">
        <HandbookChangeRequests
          changes={changes}
          onAccept={handleAcceptChange}
          onReject={handleRejectChange}
          onJumpToSection={handleJumpToSection}
          loadingId={changeActionLoading}
        />
      </div>

      {/* Freshness + Coverage */}
      <div className="grid grid-cols-2 gap-4">
        <HandbookFreshnessPanel
          check={freshnessCheck}
          running={freshnessRunning}
          onRunCheck={handleRunFreshness}
        />
        <HandbookCoveragePanel coverage={coverage} />
      </div>

      {/* Distribute Modal */}
      {showDistribute && (
        <HandbookDistributeModal
          open={showDistribute}
          onClose={() => setShowDistribute(false)}
          handbookId={handbook.id}
          onDistributed={loadData}
        />
      )}
    </div>
  )
}
