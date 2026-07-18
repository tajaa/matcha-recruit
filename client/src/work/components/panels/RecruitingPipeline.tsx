import InterviewReviewModal from './InterviewReviewModal'
import RejectCandidateModal from './RejectCandidateModal'
import PipelineProgressStrip from './PipelineProgressStrip'
import { c } from './RecruitingPipeline/constants'
import type { RecruitingPipelineProps } from './RecruitingPipeline/types'
import { usePipeline } from './RecruitingPipeline/usePipeline'
import PipelineTabs from './RecruitingPipeline/PipelineTabs'
import StatusTab from './RecruitingPipeline/StatusTab'
import PostingTab from './RecruitingPipeline/PostingTab'
import CandidateList from './RecruitingPipeline/CandidateList'

export default function RecruitingPipeline(props: RecruitingPipelineProps) {
  const { project, onSendInterviews, onSyncInterviews, onAnalyzeCandidates, offerPdfUrl } = props
  const {
    candidates, shortlistIds, dismissedIds, sections,
    tab, setTab, search, setSearch, showDismissed, setShowDismissed,
    sortKey, setSortKey, sortAsc, setSortAsc, saving, expandedId, setExpandedId,
    selectedIds, sendingInterviews, analyzing, positionInput, setPositionInput,
    showPositionPrompt, setShowPositionPrompt, reviewInterview, setReviewInterview,
    rejectTarget, setRejectTarget,
    sectionTitleEditing, setSectionTitleEditing, sectionTitleDraft, setSectionTitleDraft,
    showSaved,
    isFinalized, placeholderCount, selectableIds, hasInterviews, hasMatchScores,
    filteredCandidates, analyzedCount, interviewedCount, interviewSentCount,
    tabUnlocked, tabs, guidance,
    handleSectionContentUpdate, saveSectionTitle, handleDeleteSection, handleAddBlankSection,
    finalizePosting, handleToggleShortlist, handleRejectConfirm, handleRestoreCandidate,
    toggleSelect, toggleSelectAll, handleSendInterviews, handleAnalyze,
  } = usePipeline(props)

  return (
    <div className="flex flex-col w-full" style={{ background: c.bg }}>
      {/* Persistent pipeline progress strip */}
      <PipelineProgressStrip
        sectionCount={sections.length}
        isFinalized={isFinalized}
        candidateCount={candidates.length}
        analyzedCount={analyzedCount}
        interviewsSentCount={interviewSentCount}
        interviewedCount={interviewedCount}
        onJumpTo={(t) => {
          const target = t as typeof tab
          if (tabUnlocked[target]) setTab(target)
        }}
      />
      {/* Guidance banner */}
      {guidance && (
        <div
          className="flex items-center gap-2 px-4 py-2.5 text-xs cursor-pointer"
          style={{ background: `${c.accent}12`, borderBottom: `1px solid ${c.accent}30`, color: c.accent }}
          onClick={() => { if (tabUnlocked[guidance.action]) setTab(guidance.action) }}
        >
          <span style={{ fontSize: 14 }}>→</span>
          <span className="font-medium">{guidance.text}</span>
        </div>
      )}

      <PipelineTabs
        tabs={tabs}
        tab={tab}
        setTab={setTab}
        tabUnlocked={tabUnlocked}
        saving={saving}
        showSaved={showSaved}
        hasInterviews={hasInterviews}
        onSyncInterviews={onSyncInterviews}
        candidates={candidates}
        onAnalyzeCandidates={onAnalyzeCandidates}
        analyzing={analyzing}
        handleAnalyze={handleAnalyze}
        selectableIds={selectableIds}
        onSendInterviews={onSendInterviews}
        toggleSelectAll={toggleSelectAll}
        selectedIds={selectedIds}
        showPositionPrompt={showPositionPrompt}
        setShowPositionPrompt={setShowPositionPrompt}
        sendingInterviews={sendingInterviews}
        positionInput={positionInput}
        setPositionInput={setPositionInput}
        handleSendInterviews={handleSendInterviews}
      />

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {/* ── Status Tab ── */}
        {tab === 'status' && (
          <StatusTab
            createdAt={project.created_at}
            sectionCount={sections.length}
            isFinalized={isFinalized}
            candidateCount={candidates.length}
            analyzedCount={analyzedCount}
            interviewSentCount={interviewSentCount}
            interviewedCount={interviewedCount}
            placeholderCount={placeholderCount}
          />
        )}

        {/* ── Posting Tab — Section-based editor ── */}
        {tab === 'posting' && (
          <PostingTab
            sections={sections}
            isFinalized={isFinalized}
            saving={saving}
            placeholderCount={placeholderCount}
            sectionTitleEditing={sectionTitleEditing}
            setSectionTitleEditing={setSectionTitleEditing}
            sectionTitleDraft={sectionTitleDraft}
            setSectionTitleDraft={setSectionTitleDraft}
            saveSectionTitle={saveSectionTitle}
            handleDeleteSection={handleDeleteSection}
            handleSectionContentUpdate={handleSectionContentUpdate}
            handleAddBlankSection={handleAddBlankSection}
            finalizePosting={finalizePosting}
          />
        )}

        {/* ── Candidates / Shortlist / Interviews Tab ── */}
        {(tab === 'candidates' || tab === 'shortlist' || tab === 'interviews') && (
          <CandidateList
            tab={tab}
            search={search}
            setSearch={setSearch}
            dismissedIds={dismissedIds}
            showDismissed={showDismissed}
            setShowDismissed={setShowDismissed}
            hasMatchScores={hasMatchScores}
            sortKey={sortKey}
            sortAsc={sortAsc}
            setSortKey={setSortKey}
            setSortAsc={setSortAsc}
            filteredCandidates={filteredCandidates}
            shortlistIds={shortlistIds}
            selectedIds={selectedIds}
            expandedId={expandedId}
            setExpandedId={setExpandedId}
            onSendInterviews={onSendInterviews}
            toggleSelect={toggleSelect}
            handleToggleShortlist={handleToggleShortlist}
            setRejectTarget={setRejectTarget}
            handleRestoreCandidate={handleRestoreCandidate}
            setReviewInterview={setReviewInterview}
          />
        )}

        {/* ── Offer Tab ── */}
        {tab === 'offer' && offerPdfUrl && (
          <iframe
            src={offerPdfUrl}
            className="w-full border-0"
            style={{ height: 'calc(100vh - 160px)' }}
            title="Offer letter preview"
          />
        )}
      </div>
      {reviewInterview && (
        <InterviewReviewModal
          interviewId={reviewInterview.id}
          candidateName={reviewInterview.name}
          onClose={() => setReviewInterview(null)}
        />
      )}
      {rejectTarget && (
        <RejectCandidateModal
          candidateName={rejectTarget.name}
          candidateEmail={rejectTarget.email}
          positionTitle={project.title}
          onConfirm={handleRejectConfirm}
          onClose={() => setRejectTarget(null)}
        />
      )}
    </div>
  )
}
