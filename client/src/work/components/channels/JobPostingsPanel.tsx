import { useState, useEffect } from 'react'
import { X, Plus, Loader2, Users, UserCheck } from 'lucide-react'
import { listJobPostings } from '../../api/channelJobPostings'
import type { JobPostingSummary } from '../../api/channelJobPostings'
import CreateJobPostingModal from './CreateJobPostingModal'

interface Props {
  channelId: string
  myRole: string
  onClose: () => void
  onOpenDetail: (postingId: string) => void
}

const STATUS_BADGE: Record<string, string> = {
  pending_approval: 'bg-amber-900/40 text-amber-400 border border-amber-800/40',
  draft: 'bg-zinc-700 text-zinc-300',
  active: 'bg-emerald-900/40 text-emerald-400 border border-emerald-800/40',
  closed: 'bg-red-900/40 text-red-400 border border-red-800/40',
  rejected: 'bg-red-900/40 text-red-400 border border-red-800/40',
}

const STATUS_LABEL: Record<string, string> = {
  pending_approval: 'pending',
}

export default function JobPostingsPanel({ channelId, myRole, onClose, onOpenDetail }: Props) {
  const [postings, setPostings] = useState<JobPostingSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)

  const isManager = myRole === 'owner' || myRole === 'moderator'

  useEffect(() => {
    setLoading(true)
    listJobPostings(channelId)
      .then((data) => {
        if (isManager) {
          setPostings(data)
        } else {
          setPostings(data.filter((p) => p.status === 'active'))
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load postings'))
      .finally(() => setLoading(false))
  }, [channelId, isManager])

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-start justify-end">
        <div className="absolute inset-0 bg-black/50" onClick={onClose} />
        <div className="relative w-full max-w-lg h-full bg-zinc-900 border-l border-zinc-800 overflow-y-auto">
          {/* Header */}
          <div className="sticky top-0 bg-zinc-900 border-b border-zinc-800 px-5 py-4 flex items-center justify-between z-10">
            <h2 className="text-white font-semibold text-lg">Job Postings</h2>
            <div className="flex items-center gap-2">
              {isManager && (
                <button
                  onClick={() => setShowCreate(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg transition-colors"
                >
                  <Plus size={13} />
                  Create Posting
                </button>
              )}
              <button onClick={onClose} className="p-1.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-white">
                <X size={18} />
              </button>
            </div>
          </div>

          {loading && (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-5 h-5 text-emerald-500 animate-spin" />
            </div>
          )}

          {error && (
            <div className="px-5 py-8 text-center text-red-400 text-sm">{error}</div>
          )}

          {!loading && !error && postings.length === 0 && (
            <div className="px-5 py-16 text-center">
              <p className="text-sm text-zinc-500">No job postings yet</p>
              {isManager && (
                <p className="text-xs text-zinc-600 mt-1">Create one to start recruiting from your channel</p>
              )}
            </div>
          )}

          {!loading && !error && postings.length > 0 && (
            <div className="p-3 space-y-1">
              {postings.map((posting) => (
                <button
                  key={posting.id}
                  onClick={() => onOpenDetail(posting.id)}
                  className="w-full text-left px-4 py-3 rounded-lg hover:bg-zinc-800/60 transition-colors group"
                >
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-medium text-zinc-200 truncate">{posting.title}</span>
                        <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${STATUS_BADGE[posting.status] ?? STATUS_BADGE.draft}`}>
                          {STATUS_LABEL[posting.status] ?? posting.status}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-zinc-500">
                        <span className="flex items-center gap-1">
                          <Users size={11} />
                          {posting.applicant_count} applicant{posting.applicant_count !== 1 ? 's' : ''}
                        </span>
                        <span className="flex items-center gap-1">
                          <UserCheck size={11} />
                          {posting.invited_count} invited
                        </span>
                        <span>
                          {new Date(posting.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                        </span>
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <CreateJobPostingModal
        channelId={channelId}
        myRole={myRole}
        isOpen={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={(posting) => {
          setPostings((prev) => [posting, ...prev])
          setShowCreate(false)
        }}
      />
    </>
  )
}
