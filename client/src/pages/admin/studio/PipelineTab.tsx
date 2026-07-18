import type { UncodifiedItem } from './types'
import { usePipeline } from './PipelineTab/usePipeline'
import { CompanyFocus } from './PipelineTab/CompanyFocus'
import { QueueSection } from './PipelineTab/QueueSection'
import { ReviewSection } from './PipelineTab/ReviewSection'
import { CodifyModal } from './PipelineTab/CodifyModal'

// The DEMAND funnel, one stacked flow (no inner tabs): a company's coverage
// gap → research → staged review → approve (go live + publish) → codify.
// Section anchors let the Command Center jump straight to the right step via
// ?section=queue|review. `initialUncodifiedItems` seeds the codify chain
// directly from the Command Center's worklist (rows approved in a PAST
// session, not from a fresh approve just now) — reuses the exact same
// outcome-panel + modal UI built for the post-approve flow.
export default function PipelineTab({
  initialSection, initialUncodifiedItems, companyId, onCompanyChange,
}: {
  initialSection?: string | null
  initialUncodifiedItems?: UncodifiedItem[]
  /** Focus the tab on one tenant: the per-company job ("make THIS business
   *  whole") on the same funnel the queue below serves. Null = fleet view. */
  companyId?: string | null
  onCompanyChange?: (id: string | null) => void
}) {
  const p = usePipeline({ initialSection, initialUncodifiedItems })

  return (
    <div className="space-y-6">
      <CompanyFocus
        companyId={companyId}
        onCompanyChange={onCompanyChange}
        fitRefresh={p.fitRefresh}
        onCodifyGated={p.codifyGated}
      />

      <QueueSection
        queueRef={p.queueRef}
        pending={p.pending}
        loadingRequests={p.loadingRequests}
        openIds={p.openIds}
        selected={p.selected}
        runningId={p.runningId}
        runMessages={p.runMessages}
        fetchRequests={p.fetchRequests}
        toggleOpen={p.toggleOpen}
        toggleSelectCategory={p.toggleSelectCategory}
        runResearch={p.runResearch}
        dismissRequest={p.dismissRequest}
      />

      <ReviewSection
        reviewRef={p.reviewRef}
        justStaged={p.justStaged}
        reviewResult={p.reviewResult}
        approveResults={p.approveResults}
        loadingReview={p.loadingReview}
        reviewGroups={p.reviewGroups}
        fetchReview={p.fetchReview}
        openCodify={p.openCodify}
        approveReview={p.approveReview}
        rejectReview={p.rejectReview}
      />

      <CodifyModal
        codifyRow={p.codifyRow}
        setCodifyRow={p.setCodifyRow}
        codifyForm={p.codifyForm}
        setCodifyForm={p.setCodifyForm}
        codifyBusy={p.codifyBusy}
        codifyError={p.codifyError}
        submitCodify={p.submitCodify}
        nextUncodified={p.nextUncodified}
        openCodify={p.openCodify}
      />
    </div>
  )
}
