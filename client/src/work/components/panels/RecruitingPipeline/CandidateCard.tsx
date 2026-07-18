import { Star, MapPin, ChevronDown, ChevronUp, CheckCircle2, AlertTriangle, Video, Square, CheckSquare, XCircle, RotateCcw } from 'lucide-react'
import type { ResumeCandidate } from '../../../types'
import { c } from './constants'
import type { Tab } from './types'

interface Props {
  cand: ResumeCandidate
  tab: Tab
  shortlistIds: Set<string>
  dismissedIds: Set<string>
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

export default function CandidateCard({
  cand, tab, shortlistIds, dismissedIds, selectedIds, expandedId, setExpandedId,
  onSendInterviews, toggleSelect, handleToggleShortlist, setRejectTarget,
  handleRestoreCandidate, setReviewInterview,
}: Props) {
  const expanded = expandedId === cand.id
  const isShortlisted = shortlistIds.has(cand.id)
  const isDismissed = dismissedIds.has(cand.id)
  // `status === 'rejected'` is historical; once the candidate is
  // restored (removed from dismissed_ids) we treat them as active
  // again even though the status string sticks as a record.
  const wasRejected = cand.status === 'rejected'
  const isLowMatch = cand.match_score != null && cand.match_score < 50
  const isSelectable = tab === 'candidates' && !!cand.email && cand.status === 'analyzed' && !!onSendInterviews
  const isSelected = selectedIds.has(cand.id)
  const hasInterviewEntry = !!cand.interview_id && (cand.status === 'interview_in_progress' || cand.status === 'interview_completed')
  return (
    <div
      className="rounded-lg border transition-colors"
      style={{
        background: c.cardBg,
        borderColor: isSelected ? c.green : isDismissed ? `${c.border}80` : c.border,
        boxShadow: isSelected ? `0 0 0 1px ${c.green}` : 'none',
        opacity: isDismissed ? 0.5 : isLowMatch ? 0.8 : 1,
      }}
    >
      {/* Identity row */}
      <div className="flex items-start gap-3 px-4 pt-3.5">
        {isSelectable && (
          <button
            onClick={(e) => toggleSelect(cand.id, e)}
            className="shrink-0 mt-0.5 rounded p-0.5 hover:bg-white/5"
            style={{ color: isSelected ? c.green : c.muted }}
            title={isSelected ? 'Deselect' : 'Select for interview'}
          >
            {isSelected ? <CheckSquare size={16} /> : <Square size={16} />}
          </button>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <p
              className="text-[15px] font-semibold truncate tracking-tight"
              style={{ color: c.heading, textDecoration: isDismissed ? 'line-through' : 'none' }}
            >
              {cand.name ?? cand.filename}
            </p>
            {isDismissed && wasRejected && (
              <span
                className="text-[9px] font-medium px-1.5 py-0.5 rounded-full"
                style={{ background: '#ef444420', color: '#ef4444', border: '1px solid #ef444440' }}
              >
                Rejected
              </span>
            )}
            {cand.status === 'interview_sent' && !isDismissed && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ background: '#3b82f620', color: '#60a5fa', border: '1px solid #3b82f640' }}>
                Interview sent
              </span>
            )}
            {cand.status === 'interview_in_progress' && !isDismissed && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ background: '#f59e0b20', color: c.amber, border: `1px solid ${c.amber}40` }}>
                In progress
              </span>
            )}
            {cand.status === 'interview_completed' && !isDismissed && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ background: '#22c55e20', color: c.green, border: `1px solid ${c.green}40` }}>
                Interview done{cand.interview_score != null ? ` · ${cand.interview_score}%` : ''}
              </span>
            )}
            {cand.match_score != null && (
              <span
                className="text-[9px] font-semibold px-1.5 py-0.5 rounded-full"
                style={{
                  background: cand.match_score >= 75 ? '#22c55e20' : cand.match_score >= 50 ? '#f59e0b20' : '#ef444420',
                  color: cand.match_score >= 75 ? c.green : cand.match_score >= 50 ? c.amber : '#ef4444',
                  border: `1px solid ${cand.match_score >= 75 ? c.green : cand.match_score >= 50 ? c.amber : '#ef4444'}40`,
                }}
              >
                {cand.match_score}% match
              </span>
            )}
          </div>
          <p className="text-[12px] mt-0.5" style={{ color: c.subMuted }}>
            {cand.current_title ?? 'N/A'}
            {cand.experience_years != null && ` · ${cand.experience_years} yrs`}
          </p>
        </div>
        {cand.location && (
          <span className="flex items-center gap-1 text-[11px] shrink-0 mt-0.5" style={{ color: c.muted }}>
            <MapPin size={11} />{cand.location}
          </span>
        )}
      </div>

      {/* Action bar */}
      <div className="flex items-center flex-wrap gap-1.5 px-4 py-2.5 mt-2 border-t" style={{ borderColor: `${c.border}80` }}>
        <button
          onClick={() => handleToggleShortlist(cand.id)}
          disabled={isDismissed}
          className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-md border transition-all disabled:opacity-40 hover:bg-white/[0.04]"
          style={{
            borderColor: isShortlisted ? `${c.amber}80` : c.border,
            background: isShortlisted ? `${c.amber}15` : 'transparent',
            color: isShortlisted ? c.amber : c.subMuted,
          }}
          title={isShortlisted ? 'Remove from shortlist' : 'Add to shortlist'}
        >
          <Star size={12} fill={isShortlisted ? c.amber : 'none'} />
          {isShortlisted ? 'Shortlisted' : 'Shortlist'}
        </button>

        {!isDismissed ? (
          <button
            onClick={() => setRejectTarget({ id: cand.id, name: cand.name ?? cand.filename, email: cand.email })}
            className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-md border transition-all hover:bg-red-500/10"
            style={{ borderColor: c.border, color: c.subMuted }}
            title="Reject candidate (with optional email)"
          >
            <XCircle size={12} />
            Reject
          </button>
        ) : (
          <button
            onClick={() => handleRestoreCandidate(cand.id)}
            className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-md border transition-all hover:bg-white/[0.04]"
            style={{ borderColor: c.border, color: c.subMuted }}
            title="Restore candidate to the main list"
          >
            <RotateCcw size={12} />
            Restore
          </button>
        )}

        {hasInterviewEntry && (
          <button
            onClick={() => setReviewInterview({ id: cand.interview_id!, name: cand.name ?? 'Candidate' })}
            className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-md border transition-all hover:bg-white/[0.04]"
            style={{
              borderColor: cand.status === 'interview_completed' ? `${c.green}60` : `${c.amber}60`,
              background: cand.status === 'interview_completed' ? `${c.green}10` : `${c.amber}10`,
              color: cand.status === 'interview_completed' ? c.green : c.amber,
            }}
            title="Open interview review"
          >
            <Video size={12} />
            Review interview
          </button>
        )}

        <button
          onClick={() => setExpandedId(expanded ? null : cand.id)}
          className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-md border transition-all hover:bg-white/[0.04] ml-auto"
          style={{ borderColor: c.border, color: c.subMuted }}
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {expanded ? 'Hide details' : 'Details'}
        </button>
      </div>

      {expanded && (
        <div className="px-4 pb-4 pt-1 space-y-3" style={{ borderTop: `1px solid ${c.border}80` }}>
          {cand.summary && (
            <p className="text-[13px] leading-[1.55] mt-3" style={{ color: c.text }}>{cand.summary}</p>
          )}
          {cand.skills && cand.skills.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {cand.skills.map((s, i) => (
                <span
                  key={i}
                  className="text-[11px] font-medium px-2 py-0.5 rounded-md"
                  style={{ background: '#1a1a1a', color: c.text, border: `1px solid ${c.border}` }}
                >
                  {s}
                </span>
              ))}
            </div>
          )}
          <div className="space-y-1">
            {cand.education && <p className="text-xs" style={{ color: c.muted }}>{cand.education}</p>}
            {cand.email && <p className="text-xs" style={{ color: c.muted }}>{cand.email}</p>}
            {cand.strengths?.map((s, i) => (
              <p key={i} className="text-xs" style={{ color: c.green }}><CheckCircle2 size={10} className="inline mr-1" />{s}</p>
            ))}
            {cand.flags?.map((f, i) => (
              <p key={i} className="text-xs" style={{ color: c.amber }}><AlertTriangle size={10} className="inline mr-1" />{f}</p>
            ))}
          </div>
          {cand.match_summary && (
            <div className="pt-2" style={{ borderTop: `1px dashed ${c.border}` }}>
              <p className="text-[10px] font-medium" style={{ color: c.accent }}>
                Match Analysis{cand.match_score != null ? ` — ${cand.match_score}%` : ''}
              </p>
              <p className="text-xs mt-0.5" style={{ color: c.muted }}>{cand.match_summary}</p>
            </div>
          )}
          {cand.interview_summary && (
            <div className="pt-2" style={{ borderTop: `1px dashed ${c.border}` }}>
              <p className="text-[10px] font-medium" style={{ color: '#60a5fa' }}>
                <Video size={10} className="inline mr-1" />Interview{cand.interview_score != null ? ` — ${cand.interview_score}%` : ''}
              </p>
              <p className="text-xs mt-0.5" style={{ color: c.muted }}>{cand.interview_summary}</p>
            </div>
          )}
          {wasRejected && cand.rejection_reason && (
            <div className="pt-2" style={{ borderTop: `1px dashed ${c.border}` }}>
              <p className="text-[10px] font-medium" style={{ color: '#ef4444' }}>
                Rejection note (internal)
              </p>
              <p className="text-xs mt-0.5" style={{ color: c.muted }}>{cand.rejection_reason}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
