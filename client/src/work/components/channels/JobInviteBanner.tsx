import { useState, useEffect } from 'react'
import { Briefcase } from 'lucide-react'
import { getJobPosting } from '../../api/channelJobPostings'

interface Props {
  channelId: string
  postingId: string
  onView: () => void
}

export default function JobInviteBanner({ channelId, postingId, onView }: Props) {
  const [title, setTitle] = useState<string | null>(null)

  useEffect(() => {
    getJobPosting(channelId, postingId)
      .then((p) => setTitle(p.title))
      .catch(() => {})
  }, [channelId, postingId])

  if (!title) return null

  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b border-emerald-800/40 bg-emerald-950/30">
      <Briefcase size={14} className="text-emerald-400 shrink-0" />
      <span className="text-xs text-emerald-300 truncate flex-1">
        You're invited to apply for: <span className="font-medium text-emerald-200">{title}</span>
      </span>
      <button
        onClick={onView}
        className="text-[10px] font-semibold uppercase tracking-wider px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white transition-colors shrink-0"
      >
        View
      </button>
    </div>
  )
}
