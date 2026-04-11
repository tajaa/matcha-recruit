import { useState, useEffect } from 'react'
import { X, Loader2, MapPin, DollarSign, Calendar, Send, XCircle, ChevronDown } from 'lucide-react'
import {
  getJobPosting,
  listApplicants,
  inviteToPosting,
  submitApplication,
  withdrawApplication,
  updateApplicationStatus,
  cancelJobPosting,
  closeJobPosting,
} from '../../api/channelJobPostings'
import type { JobPostingDetail as JobPostingDetailData, ApplicationSummary } from '../../api/channelJobPostings'

interface Props {
  channelId: string
  postingId: string
  myRole: string
  onClose: () => void
}

const APP_STATUS_BADGE: Record<string, string> = {
  submitted: 'bg-blue-900/40 text-blue-400',
  reviewed: 'bg-amber-900/40 text-amber-400',
  shortlisted: 'bg-emerald-900/40 text-emerald-400',
  rejected: 'bg-red-900/40 text-red-400',
}

export default function JobPostingDetail({ channelId, postingId, myRole, onClose }: Props) {
  const [posting, setPosting] = useState<JobPostingDetailData | null>(null)
  const [applicants, setApplicants] = useState<ApplicationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Invite state
  const [inviteInput, setInviteInput] = useState('')
  const [inviting, setInviting] = useState(false)
  const [inviteMsg, setInviteMsg] = useState('')

  // Apply state (for subscribers)
  const [coverLetter, setCoverLetter] = useState('')
  const [applying, setApplying] = useState(false)
  const [applyMsg, setApplyMsg] = useState('')

  // Status update state
  const [updatingId, setUpdatingId] = useState<string | null>(null)
  const [reviewerNotes, setReviewerNotes] = useState('')
  const [notesForApp, setNotesForApp] = useState<string | null>(null)

  // Action state
  const [actionLoading, setActionLoading] = useState(false)

  const isManager = myRole === 'owner' || myRole === 'moderator'

  useEffect(() => {
    setLoading(true)
    const promises: Promise<unknown>[] = [
      getJobPosting(channelId, postingId).then(setPosting),
    ]
    if (isManager) {
      promises.push(listApplicants(channelId, postingId).then(setApplicants))
    }
    Promise.all(promises)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load posting'))
      .finally(() => setLoading(false))
  }, [channelId, postingId, isManager])

  async function handleInvite() {
    const ids = inviteInput
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    if (ids.length === 0) return
    setInviting(true)
    setInviteMsg('')
    try {
      await inviteToPosting(channelId, postingId, ids)
      setInviteMsg(`Invited ${ids.length} user${ids.length > 1 ? 's' : ''}`)
      setInviteInput('')
    } catch (err) {
      setInviteMsg(err instanceof Error ? err.message : 'Failed to invite')
    }
    setInviting(false)
  }

  async function handleApply() {
    setApplying(true)
    setApplyMsg('')
    try {
      await submitApplication(channelId, postingId, coverLetter.trim() || undefined)
      setApplyMsg('Application submitted!')
      // Refresh posting to get updated my_application
      const updated = await getJobPosting(channelId, postingId)
      setPosting(updated)
    } catch (err) {
      setApplyMsg(err instanceof Error ? err.message : 'Failed to apply')
    }
    setApplying(false)
  }

  async function handleWithdraw() {
    setApplying(true)
    try {
      await withdrawApplication(channelId, postingId)
      const updated = await getJobPosting(channelId, postingId)
      setPosting(updated)
    } catch (err) {
      setApplyMsg(err instanceof Error ? err.message : 'Failed to withdraw')
    }
    setApplying(false)
  }

  async function handleStatusUpdate(applicationId: string, status: string) {
    setUpdatingId(applicationId)
    try {
      await updateApplicationStatus(channelId, postingId, applicationId, status, reviewerNotes.trim() || undefined)
      setApplicants((prev) =>
        prev.map((a) => (a.id === applicationId ? { ...a, status, reviewed_at: new Date().toISOString() } : a))
      )
      setNotesForApp(null)
      setReviewerNotes('')
    } catch {}
    setUpdatingId(null)
  }

  async function handleCancel() {
    setActionLoading(true)
    try {
      await cancelJobPosting(channelId, postingId)
      const updated = await getJobPosting(channelId, postingId)
      setPosting(updated)
    } catch {}
    setActionLoading(false)
  }

  async function handleClose() {
    setActionLoading(true)
    try {
      await closeJobPosting(channelId, postingId)
      const updated = await getJobPosting(channelId, postingId)
      setPosting(updated)
    } catch {}
    setActionLoading(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-2xl h-full max-h-[90vh] mt-[5vh] bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-zinc-900 border-b border-zinc-800 px-5 py-4 flex items-center justify-between z-10">
          <h2 className="text-white font-semibold text-lg truncate">
            {posting?.title ?? 'Job Posting'}
          </h2>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-white">
            <X size={18} />
          </button>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-5 h-5 text-emerald-500 animate-spin" />
          </div>
        )}

        {error && (
          <div className="px-5 py-8 text-center text-red-400 text-sm">{error}</div>
        )}

        {posting && !loading && (
          <div className="p-5 space-y-6">
            {/* Invite banner for subscribers */}
            {!isManager && posting.my_invitation && !posting.my_application && (
              <div className="bg-emerald-950/30 border border-emerald-800/40 rounded-lg px-4 py-3">
                <p className="text-sm text-emerald-300">You were invited to apply for this position</p>
                <p className="text-xs text-emerald-500 mt-0.5">
                  Invited {new Date(posting.my_invitation.invited_at).toLocaleDateString()}
                </p>
              </div>
            )}

            {/* Status + meta */}
            <div className="flex flex-wrap items-center gap-3">
              <span className={`text-xs font-bold uppercase px-2 py-1 rounded ${
                posting.status === 'active'
                  ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-800/40'
                  : posting.status === 'closed'
                    ? 'bg-red-900/40 text-red-400 border border-red-800/40'
                    : 'bg-zinc-700 text-zinc-300'
              }`}>
                {posting.status}
              </span>
              {posting.subscription_status && (
                <span className="text-xs text-zinc-500">
                  Subscription: {posting.subscription_status}
                </span>
              )}
              {posting.paid_through && (
                <span className="text-xs text-zinc-500">
                  Paid through {new Date(posting.paid_through).toLocaleDateString()}
                </span>
              )}
            </div>

            {/* Details */}
            <div className="space-y-3">
              {posting.location && (
                <div className="flex items-center gap-2 text-sm text-zinc-400">
                  <MapPin size={14} className="shrink-0" />
                  <span>{posting.location}</span>
                </div>
              )}
              {posting.compensation_summary && (
                <div className="flex items-center gap-2 text-sm text-zinc-400">
                  <DollarSign size={14} className="shrink-0" />
                  <span>{posting.compensation_summary}</span>
                </div>
              )}
              <div className="flex items-center gap-2 text-xs text-zinc-500">
                <Calendar size={12} className="shrink-0" />
                <span>Posted {new Date(posting.created_at).toLocaleDateString()}</span>
              </div>
            </div>

            {posting.description && (
              <div>
                <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Description</h3>
                <p className="text-sm text-zinc-300 whitespace-pre-wrap">{posting.description}</p>
              </div>
            )}

            {posting.requirements && (
              <div>
                <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Requirements</h3>
                <p className="text-sm text-zinc-300 whitespace-pre-wrap">{posting.requirements}</p>
              </div>
            )}

            {/* ---- Manager sections ---- */}
            {isManager && (
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
                  {applicants.length === 0 ? (
                    <p className="text-xs text-zinc-600">No applications yet</p>
                  ) : (
                    <div className="space-y-2">
                      {applicants.map((app) => (
                        <div key={app.id} className="bg-zinc-800/50 border border-zinc-800 rounded-lg px-4 py-3">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-sm font-medium text-zinc-200">{app.applicant_name}</p>
                              <p className="text-xs text-zinc-500">{app.applicant_email}</p>
                              {app.cover_letter && (
                                <p className="text-xs text-zinc-400 mt-1.5 line-clamp-2">{app.cover_letter}</p>
                              )}
                              <p className="text-[10px] text-zinc-600 mt-1">
                                Applied {new Date(app.submitted_at).toLocaleDateString()}
                                {app.reviewed_at && ` \u00b7 Reviewed ${new Date(app.reviewed_at).toLocaleDateString()}`}
                              </p>
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
                        </div>
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
            )}

            {/* ---- Subscriber sections ---- */}
            {!isManager && (
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
                ) : posting.status === 'active' ? (
                  <div className="border-t border-zinc-800 pt-4">
                    <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Apply</h3>
                    <textarea
                      value={coverLetter}
                      onChange={(e) => setCoverLetter(e.target.value)}
                      placeholder="Cover letter (optional)"
                      rows={4}
                      className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600 resize-none mb-3"
                    />
                    <button
                      onClick={handleApply}
                      disabled={applying}
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
            )}
          </div>
        )}
      </div>
    </div>
  )
}
