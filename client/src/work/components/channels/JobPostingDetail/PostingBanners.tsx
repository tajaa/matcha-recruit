import type { JobPostingDetail as JobPostingDetailData } from '../../../api/channelJobPostings'

interface Props {
  posting: JobPostingDetailData
  myRole: string
  isManager: boolean
  actionLoading: boolean
  onApprove: () => void
  onReject: () => void
  onStartCheckout: () => void
}

export function PostingBanners({
  posting,
  myRole,
  isManager,
  actionLoading,
  onApprove,
  onReject,
  onStartCheckout,
}: Props) {
  return (
    <>
      {/* Invite banner for subscribers */}
      {!isManager && posting.my_invitation && !posting.my_application && (
        <div className="bg-emerald-950/30 border border-emerald-800/40 rounded-lg px-4 py-3">
          <p className="text-sm text-emerald-300">You were invited to apply for this position</p>
          <p className="text-xs text-emerald-500 mt-0.5">
            Invited {new Date(posting.my_invitation.invited_at).toLocaleDateString()}
          </p>
        </div>
      )}

      {/* Approval state banner */}
      {posting.status === 'pending_approval' && (
        <div className="rounded-lg border border-amber-800/40 bg-amber-950/30 px-4 py-3">
          <p className="text-sm text-amber-300 font-medium">Awaiting owner approval</p>
          <p className="text-xs text-amber-400/80 mt-1">
            {myRole === 'owner'
              ? 'Approve to let the recruiter complete checkout, or reject to block it.'
              : 'The channel owner has to approve this posting before it goes live.'}
          </p>
          {myRole === 'owner' && (
            <div className="flex items-center gap-2 mt-3">
              <button
                onClick={onApprove}
                disabled={actionLoading}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded transition-colors disabled:opacity-50"
              >
                {actionLoading ? 'Working…' : 'Approve'}
              </button>
              <button
                onClick={onReject}
                disabled={actionLoading}
                className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-medium rounded transition-colors disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          )}
        </div>
      )}

      {posting.status === 'rejected' && (
        <div className="rounded-lg border border-red-800/40 bg-red-950/30 px-4 py-3">
          <p className="text-sm text-red-300 font-medium">Rejected</p>
          {posting.rejected_reason && (
            <p className="text-xs text-red-400/80 mt-1">{posting.rejected_reason}</p>
          )}
        </div>
      )}

      {posting.status === 'draft' && posting.posted_by && isManager && (
        <div className="rounded-lg border border-blue-800/40 bg-blue-950/30 px-4 py-3 flex items-center justify-between gap-3">
          <div>
            <p className="text-sm text-blue-300 font-medium">Approved — ready for checkout</p>
            <p className="text-xs text-blue-400/80 mt-1">
              Complete the monthly subscription to activate this posting.
            </p>
          </div>
          <button
            onClick={onStartCheckout}
            disabled={actionLoading}
            className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded transition-colors shrink-0 disabled:opacity-50"
          >
            {actionLoading ? 'Opening…' : 'Pay now'}
          </button>
        </div>
      )}
    </>
  )
}
