import { Briefcase } from 'lucide-react'
import type { OpenPostingSummary } from '../../api/channelJobPostings'

interface Props {
  postings: OpenPostingSummary[]
  onView: (postingId: string) => void
}

/** Banner shown at the top of a channel when there are active open-to-all
 *  job postings the current member can apply to. Stacks multiple postings
 *  in a compact row; clicking one opens the posting detail pane.
 */
export default function ChannelOpenRoleBanner({ postings, onView }: Props) {
  if (postings.length === 0) return null
  // Show the most recent posting prominently; collapse the rest into a count.
  const [primary, ...rest] = postings

  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b border-emerald-800/40 bg-emerald-950/30">
      <Briefcase size={14} className="text-emerald-400 shrink-0" />
      <div className="flex-1 min-w-0 flex items-center gap-2">
        <span className="text-xs text-emerald-300 truncate">
          Open role:{' '}
          <span className="font-medium text-emerald-200">{primary.title}</span>
          {primary.location && (
            <span className="text-emerald-500/70"> · {primary.location}</span>
          )}
          {primary.compensation_summary && (
            <span className="text-emerald-500/70"> · {primary.compensation_summary}</span>
          )}
        </span>
        {rest.length > 0 && (
          <span className="text-[10px] text-emerald-500 shrink-0">
            +{rest.length} more
          </span>
        )}
      </div>
      <button
        onClick={() => onView(primary.id)}
        disabled={primary.already_applied}
        className="text-[10px] font-semibold uppercase tracking-wider px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 disabled:bg-emerald-900 disabled:text-emerald-500 text-white transition-colors shrink-0"
      >
        {primary.already_applied ? 'Applied' : 'Apply'}
      </button>
    </div>
  )
}
