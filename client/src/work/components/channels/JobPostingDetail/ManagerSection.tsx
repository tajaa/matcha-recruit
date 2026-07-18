import { Loader2, Send, X, XCircle } from 'lucide-react'
import { ApplicantCard } from './ApplicantCard'
import type { JobPostingDetailController } from './useJobPostingDetail'

export function ManagerSection({ c }: { c: JobPostingDetailController }) {
  const {
    posting,
    applicants,
    inviteInput,
    setInviteInput,
    inviting,
    inviteMsg,
    tier,
    upgrading,
    actionLoading,
    handleInvite,
    handleUpgradeRecruiter,
    handleCancel,
    handleClose,
  } = c
  if (!posting) return null
  return (
    <>
      {/* Invite subscribers */}
      <div>
        <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Invite Subscribers</h3>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={inviteInput}
            onChange={(e) => setInviteInput(e.target.value)}
            placeholder="Comma-separated user IDs"
            className="flex-1 px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600"
          />
          <button
            onClick={handleInvite}
            disabled={!inviteInput.trim() || inviting}
            className="flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            {inviting ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Invite
          </button>
        </div>
        {inviteMsg && (
          <p className="text-xs text-zinc-500 mt-1.5">{inviteMsg}</p>
        )}
      </div>

      {/* Applicants */}
      <div>
        <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
          Applicants ({applicants.length})
        </h3>
        {applicants.length > 0 && tier && !tier.is_recruiter && (
          <div className="mb-3 rounded-lg border border-emerald-800/40 bg-emerald-950/30 px-4 py-3 flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-emerald-300">
                Upgrade to Matcha Recruiter to read parsed resumes
              </p>
              <p className="text-xs text-emerald-400/80 mt-1 leading-relaxed">
                $30/month. Unlocks skills, experience, strengths, and live profile fetch for every applicant on every posting. Cover letters and applicant contact info stay visible without upgrading.
              </p>
            </div>
            <button
              onClick={handleUpgradeRecruiter}
              disabled={upgrading}
              className="shrink-0 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded transition-colors disabled:opacity-50"
            >
              {upgrading ? 'Opening…' : 'Upgrade'}
            </button>
          </div>
        )}
        {applicants.length === 0 ? (
          <p className="text-xs text-zinc-600">No applications yet</p>
        ) : (
          <div className="space-y-2">
            {applicants.map((app) => (
              <ApplicantCard key={app.id} app={app} c={c} />
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      {posting.status !== 'closed' && (
        <div className="flex items-center gap-3 pt-2 border-t border-zinc-800">
          {posting.subscription_status === 'active' && (
            <button
              onClick={handleCancel}
              disabled={actionLoading}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-amber-400 hover:bg-amber-900/20 rounded-lg transition-colors disabled:opacity-50"
            >
              <XCircle size={13} />
              Cancel Subscription
            </button>
          )}
          <button
            onClick={handleClose}
            disabled={actionLoading}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-red-400 hover:bg-red-900/20 rounded-lg transition-colors disabled:opacity-50"
          >
            <X size={13} />
            Close Posting
          </button>
        </div>
      )}
    </>
  )
}
