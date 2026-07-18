import { X, Loader2 } from 'lucide-react'
import type { Props } from './JobPostingDetail/types'
import { useJobPostingDetail } from './JobPostingDetail/useJobPostingDetail'
import { PostingBanners } from './JobPostingDetail/PostingBanners'
import { PostingMeta } from './JobPostingDetail/PostingMeta'
import { ManagerSection } from './JobPostingDetail/ManagerSection'
import { SubscriberSection } from './JobPostingDetail/SubscriberSection'
import { NoResumeModal } from './JobPostingDetail/NoResumeModal'

export default function JobPostingDetail({ channelId, postingId, myRole, onClose }: Props) {
  const c = useJobPostingDetail(channelId, postingId, myRole)
  const { brand, posting, loading, error, isManager, showNoResumeModal, setShowNoResumeModal } = c

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
            <PostingBanners
              posting={posting}
              myRole={myRole}
              isManager={isManager}
              actionLoading={c.actionLoading}
              onApprove={c.handleApprove}
              onReject={c.handleReject}
              onStartCheckout={c.handleStartCheckout}
            />

            <PostingMeta posting={posting} />

            {/* ---- Manager sections ---- */}
            {isManager && <ManagerSection c={c} />}

            {/* ---- Subscriber sections ---- */}
            {!isManager && <SubscriberSection c={c} />}
          </div>
        )}
      </div>

      {/* No-resume guardrail modal */}
      {showNoResumeModal && (
        <NoResumeModal brand={brand} onClose={() => setShowNoResumeModal(false)} />
      )}
    </div>
  )
}
