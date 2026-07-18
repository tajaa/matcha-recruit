import { MapPin, DollarSign, Calendar, Users, UserCheck } from 'lucide-react'
import type { JobPostingDetail as JobPostingDetailData } from '../../../api/channelJobPostings'

export function PostingMeta({ posting }: { posting: JobPostingDetailData }) {
  return (
    <>
      {/* Status + meta */}
      <div className="flex flex-wrap items-center gap-3">
        <span className={`text-xs font-bold uppercase px-2 py-1 rounded ${
          posting.status === 'active'
            ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-800/40'
            : posting.status === 'closed' || posting.status === 'rejected'
              ? 'bg-red-900/40 text-red-400 border border-red-800/40'
              : posting.status === 'pending_approval'
                ? 'bg-amber-900/40 text-amber-400 border border-amber-800/40'
                : 'bg-zinc-700 text-zinc-300'
        }`}>
          {posting.status === 'pending_approval' ? 'pending' : posting.status}
        </span>
        <span className={`text-xs font-medium inline-flex items-center gap-1 px-2 py-1 rounded border ${
          posting.open_to_all
            ? 'bg-emerald-950/40 text-emerald-400 border-emerald-800/40'
            : 'bg-blue-950/40 text-blue-400 border-blue-800/40'
        }`}>
          {posting.open_to_all ? <Users size={11} /> : <UserCheck size={11} />}
          {posting.open_to_all ? 'Open to all members' : 'Invite only'}
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
    </>
  )
}
