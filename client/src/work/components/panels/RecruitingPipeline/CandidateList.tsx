import { Search, ChevronDown, ChevronUp, Eye, EyeOff } from 'lucide-react'
import type { ResumeCandidate } from '../../../types'
import { c } from './constants'
import type { Tab, SortKey } from './types'
import CandidateCard from './CandidateCard'

interface Props {
  tab: Tab
  search: string
  setSearch: (v: string) => void
  dismissedIds: Set<string>
  showDismissed: boolean
  setShowDismissed: (v: boolean) => void
  hasMatchScores: boolean
  sortKey: SortKey
  sortAsc: boolean
  setSortKey: (k: SortKey) => void
  setSortAsc: (v: boolean) => void
  filteredCandidates: ResumeCandidate[]
  shortlistIds: Set<string>
  selectedIds: Set<string>
  expandedId: string | null
  setExpandedId: (id: string | null) => void
  onSendInterviews?: (candidateIds: string[], positionTitle?: string) => Promise<void>
  toggleSelect: (id: string, e: React.MouseEvent) => void
  handleToggleShortlist: (candidateId: string) => Promise<void>
  setRejectTarget: (t: { id: string; name: string; email: string | null } | null) => void
  handleRestoreCandidate: (candidateId: string) => Promise<void>
  setReviewInterview: (t: { id: string; name: string } | null) => void
}

export default function CandidateList({
  tab, search, setSearch, dismissedIds, showDismissed, setShowDismissed, hasMatchScores,
  sortKey, sortAsc, setSortKey, setSortAsc, filteredCandidates, shortlistIds, selectedIds,
  expandedId, setExpandedId, onSendInterviews, toggleSelect, handleToggleShortlist,
  setRejectTarget, handleRestoreCandidate, setReviewInterview,
}: Props) {
  return (
    <div>
      {/* Search + Sort */}
      <div className="px-3 py-2 flex items-center gap-2" style={{ borderBottom: `1px solid ${c.border}` }}>
        <div className="relative flex-1">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: c.muted }} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, title, skills..."
            className="w-full text-xs rounded pl-7 pr-2 py-1.5 border focus:outline-none"
            style={{ background: '#1a1a1a', color: c.text, borderColor: c.border }}
          />
        </div>
        {tab === 'candidates' && dismissedIds.size > 0 && (
          <button
            onClick={() => setShowDismissed(!showDismissed)}
            className="flex items-center gap-1 text-[10px] font-medium px-2 py-1 rounded"
            style={{ color: showDismissed ? c.accent : c.muted }}
            title={showDismissed ? 'Hide rejected' : `Show ${dismissedIds.size} rejected`}
          >
            {showDismissed ? <EyeOff size={10} /> : <Eye size={10} />}
            {showDismissed ? 'Hide rejected' : `Show rejected (${dismissedIds.size})`}
          </button>
        )}
        {(hasMatchScores ? ['match_score', 'experience_years', 'name', 'location'] : ['experience_years', 'name', 'location']).map((key) => {
          const labels: Record<string, string> = { match_score: 'Match', experience_years: 'Exp', name: 'Name', location: 'Loc' }
          const active = sortKey === key
          return (
            <button
              key={key}
              onClick={() => { if (active) setSortAsc(!sortAsc); else { setSortKey(key as SortKey); setSortAsc(key === 'name') } }}
              className="text-[10px] font-medium px-2 py-1 rounded"
              style={{ color: active ? c.accent : c.muted }}
            >
              {labels[key]}
              {active && (sortAsc ? <ChevronUp size={8} className="inline ml-0.5" /> : <ChevronDown size={8} className="inline ml-0.5" />)}
            </button>
          )
        })}
      </div>

      {/* Candidate list */}
      <div className="p-3 space-y-2">
        {filteredCandidates.length === 0 && (
          <div className="text-center py-8" style={{ color: c.muted }}>
            <p className="text-xs">
              {tab === 'candidates' ? 'No candidates yet. Drop resumes in the chat.' :
               tab === 'shortlist' ? 'No candidates shortlisted.' :
               'No interviews yet.'}
            </p>
          </div>
        )}
        {filteredCandidates.map((cand) => (
          <CandidateCard
            key={cand.id}
            cand={cand}
            tab={tab}
            shortlistIds={shortlistIds}
            dismissedIds={dismissedIds}
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
        ))}
      </div>
    </div>
  )
}
