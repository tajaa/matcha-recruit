import { Link } from 'react-router-dom'
import { Loader2, FileText } from 'lucide-react'
import { APP_STATUS_BADGE } from './constants'
import type { JobPostingDetailController } from './useJobPostingDetail'

export function SubscriberSection({ c }: { c: JobPostingDetailController }) {
  const {
    posting,
    coverLetter,
    setCoverLetter,
    applying,
    applyMsg,
    myResume,
    myResumeLoaded,
    handleApply,
    handleWithdraw,
  } = c
  if (!posting) return null
  return (
    <>
      {posting.my_application ? (
        <div className="border-t border-zinc-800 pt-4">
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Your Application</h3>
          <div className="bg-zinc-800/50 border border-zinc-800 rounded-lg px-4 py-3">
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${APP_STATUS_BADGE[posting.my_application.status] ?? 'bg-zinc-700 text-zinc-400'}`}>
                {posting.my_application.status}
              </span>
              <span className="text-xs text-zinc-500">
                Submitted {new Date(posting.my_application.submitted_at).toLocaleDateString()}
              </span>
            </div>
            <button
              onClick={handleWithdraw}
              disabled={applying}
              className="mt-2 text-xs text-red-400 hover:text-red-300 transition-colors"
            >
              {applying ? 'Withdrawing...' : 'Withdraw Application'}
            </button>
          </div>
        </div>
      ) : posting.status === 'active' && posting.i_can_apply !== false ? (
        <div className="border-t border-zinc-800 pt-4">
          <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Apply</h3>
          {myResumeLoaded && myResume && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-950/20 border border-emerald-800/30 mb-3">
              <FileText size={13} className="text-emerald-400 shrink-0" />
              <span className="text-xs text-emerald-300">
                Applying with resume: <span className="font-medium">{myResume.filename}</span>
              </span>
            </div>
          )}
          {myResumeLoaded && !myResume && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-950/20 border border-amber-800/30 mb-3">
              <FileText size={13} className="text-amber-400 shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-xs text-amber-300">You need a profile resume to apply.</p>
                <Link
                  to="/settings"
                  className="text-[11px] text-amber-200 underline hover:text-white"
                >
                  Upload one in Settings →
                </Link>
              </div>
            </div>
          )}
          <textarea
            value={coverLetter}
            onChange={(e) => setCoverLetter(e.target.value)}
            placeholder="Cover letter (optional)"
            rows={4}
            className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600 resize-none mb-3"
          />
          <button
            onClick={handleApply}
            disabled={applying || !myResumeLoaded}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            {applying && <Loader2 size={14} className="animate-spin" />}
            Submit Application
          </button>
          {applyMsg && (
            <p className="text-xs text-zinc-500 mt-2">{applyMsg}</p>
          )}
        </div>
      ) : null}
    </>
  )
}
