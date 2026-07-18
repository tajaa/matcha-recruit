import { Loader2, ChevronDown, FileText, ExternalLink } from 'lucide-react'
import type { ApplicationSummary } from '../../../api/channelJobPostings'
import { APP_STATUS_BADGE } from './constants'
import { ParsedResumeCard } from './ParsedResumeCard'
import type { JobPostingDetailController } from './useJobPostingDetail'

interface Props {
  app: ApplicationSummary
  c: JobPostingDetailController
}

export function ApplicantCard({ app, c }: Props) {
  const {
    expandedSnapshot,
    setExpandedSnapshot,
    liveResumes,
    liveLoading,
    updatingId,
    notesForApp,
    setNotesForApp,
    reviewerNotes,
    setReviewerNotes,
    upgrading,
    handleStatusUpdate,
    handleUpgradeRecruiter,
    loadLiveResume,
  } = c
  const expanded = expandedSnapshot === app.id
  const live = liveResumes[app.applicant_id]
  return (
    <div key={app.id} className="bg-zinc-800/50 border border-zinc-800 rounded-lg px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-zinc-200">{app.applicant_name}</p>
          <p className="text-xs text-zinc-500">{app.applicant_email}</p>
          {app.cover_letter && (
            <p className="text-xs text-zinc-400 mt-1.5 line-clamp-2">{app.cover_letter}</p>
          )}
          <p className="text-[10px] text-zinc-600 mt-1">
            Applied {new Date(app.submitted_at).toLocaleDateString()}
            {app.reviewed_at && ` · Reviewed ${new Date(app.reviewed_at).toLocaleDateString()}`}
          </p>
          {app.resume_snapshot && (
            <button
              onClick={() => setExpandedSnapshot(expanded ? null : app.id)}
              className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-emerald-400 hover:text-emerald-300"
            >
              <FileText size={11} />
              {expanded ? 'Hide parsed resume' : 'View parsed resume'}
            </button>
          )}
          {!app.resume_snapshot && app.resume_locked && (
            <button
              onClick={handleUpgradeRecruiter}
              disabled={upgrading}
              className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-amber-400 hover:text-amber-300 disabled:opacity-50"
            >
              <FileText size={11} />
              Parsed resume locked — upgrade to view
            </button>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${APP_STATUS_BADGE[app.status] ?? 'bg-zinc-700 text-zinc-400'}`}>
            {app.status}
          </span>
          <div className="relative">
            <button
              onClick={() => setNotesForApp(notesForApp === app.id ? null : app.id)}
              disabled={updatingId === app.id}
              className="p-1 rounded hover:bg-zinc-700 text-zinc-500 hover:text-white"
            >
              {updatingId === app.id ? <Loader2 size={14} className="animate-spin" /> : <ChevronDown size={14} />}
            </button>
            {notesForApp === app.id && (
              <div className="absolute right-0 mt-1 w-48 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl z-20 py-1">
                {['reviewed', 'shortlisted', 'rejected'].map((s) => (
                  <button
                    key={s}
                    onClick={() => handleStatusUpdate(app.id, s)}
                    className="w-full text-left px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 capitalize"
                  >
                    {s}
                  </button>
                ))}
                <div className="border-t border-zinc-700 mt-1 pt-1 px-3 pb-2">
                  <input
                    type="text"
                    value={reviewerNotes}
                    onChange={(e) => setReviewerNotes(e.target.value)}
                    placeholder="Notes (optional)"
                    className="w-full px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-xs text-white placeholder:text-zinc-600 focus:outline-none"
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
      {expanded && app.resume_snapshot && (
        <div className="mt-3 pt-3 border-t border-zinc-800 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase tracking-wider text-zinc-500">Submitted snapshot</span>
            <button
              onClick={() => loadLiveResume(app.applicant_id)}
              disabled={liveLoading === app.applicant_id}
              className="inline-flex items-center gap-1.5 text-[10px] text-zinc-400 hover:text-zinc-200"
            >
              {liveLoading === app.applicant_id ? (
                <Loader2 size={10} className="animate-spin" />
              ) : (
                <ExternalLink size={10} />
              )}
              {live !== undefined ? 'Compare live' : 'Load live profile'}
            </button>
          </div>
          <ParsedResumeCard data={app.resume_snapshot} />
          {live && (
            <>
              <div className="text-[10px] uppercase tracking-wider text-zinc-500">Current profile</div>
              <ParsedResumeCard data={live.parsed_data} />
            </>
          )}
          {live === null && (
            <p className="text-[11px] text-zinc-500 italic">Applicant has no live profile resume.</p>
          )}
        </div>
      )}
    </div>
  )
}
