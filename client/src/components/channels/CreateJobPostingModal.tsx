import { useEffect, useState } from 'react'
import { X, Loader2, Users, UserCheck } from 'lucide-react'
import { createJobPosting, createJobPostingCheckout, getJobPostingFee } from '../../api/channelJobPostings'
import type { JobPostingSummary } from '../../api/channelJobPostings'

interface Props {
  channelId: string
  isOpen: boolean
  onClose: () => void
  onCreated: (posting: JobPostingSummary) => void
}

type Targeting = 'open_to_all' | 'targeted'

export default function CreateJobPostingModal({ channelId, isOpen, onClose, onCreated }: Props) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [requirements, setRequirements] = useState('')
  const [compensationSummary, setCompensationSummary] = useState('')
  const [location, setLocation] = useState('')
  const [targeting, setTargeting] = useState<Targeting>('open_to_all')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [feeCents, setFeeCents] = useState<number | null>(null)
  const [feeIsDefault, setFeeIsDefault] = useState(true)

  useEffect(() => {
    if (!isOpen) return
    getJobPostingFee(channelId)
      .then((res) => {
        setFeeCents(res.fee_cents)
        setFeeIsDefault(res.default_used)
      })
      .catch(() => {})
  }, [isOpen, channelId])

  if (!isOpen) return null

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim()) return
    setSubmitting(true)
    setError('')
    try {
      const posting = await createJobPosting(channelId, {
        title: title.trim(),
        description: description.trim() || undefined,
        requirements: requirements.trim() || undefined,
        compensation_summary: compensationSummary.trim() || undefined,
        location: location.trim() || undefined,
        open_to_all: targeting === 'open_to_all',
      })
      onCreated(posting)
      const { checkout_url } = await createJobPostingCheckout(channelId, posting.id)
      window.location.href = checkout_url
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create posting')
      setSubmitting(false)
    }
  }

  const feeLabel =
    feeCents == null
      ? feeIsDefault
        ? 'Standard monthly subscription'
        : 'Channel fee not set'
      : `$${(feeCents / 100).toFixed(2)} / month`

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
          <h2 className="text-white font-semibold">Create Job Posting</h2>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-white">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="text-sm text-red-400 bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Title *</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Senior React Developer"
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the role and responsibilities..."
              rows={3}
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600 resize-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Requirements</label>
            <textarea
              value={requirements}
              onChange={(e) => setRequirements(e.target.value)}
              placeholder="List qualifications and requirements..."
              rows={3}
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600 resize-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Compensation</label>
              <input
                type="text"
                value={compensationSummary}
                onChange={(e) => setCompensationSummary(e.target.value)}
                placeholder="e.g. $120k-$150k"
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">Location</label>
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="e.g. Remote, NYC"
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">Who can apply?</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setTargeting('open_to_all')}
                className={`flex items-start gap-2 rounded-lg border p-3 text-left transition-colors ${
                  targeting === 'open_to_all'
                    ? 'border-emerald-600 bg-emerald-950/30'
                    : 'border-zinc-700 hover:border-zinc-600 bg-zinc-800/50'
                }`}
              >
                <Users size={16} className={targeting === 'open_to_all' ? 'text-emerald-400 mt-0.5' : 'text-zinc-500 mt-0.5'} />
                <div>
                  <div className="text-xs font-medium text-zinc-100">Open to all</div>
                  <div className="text-[11px] text-zinc-500 mt-0.5">Every member sees a banner and can apply.</div>
                </div>
              </button>
              <button
                type="button"
                onClick={() => setTargeting('targeted')}
                className={`flex items-start gap-2 rounded-lg border p-3 text-left transition-colors ${
                  targeting === 'targeted'
                    ? 'border-emerald-600 bg-emerald-950/30'
                    : 'border-zinc-700 hover:border-zinc-600 bg-zinc-800/50'
                }`}
              >
                <UserCheck size={16} className={targeting === 'targeted' ? 'text-emerald-400 mt-0.5' : 'text-zinc-500 mt-0.5'} />
                <div>
                  <div className="text-xs font-medium text-zinc-100">Invite specific</div>
                  <div className="text-[11px] text-zinc-500 mt-0.5">Pick members on the detail page after creating.</div>
                </div>
              </button>
            </div>
          </div>

          <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2 text-[11px] text-zinc-400">
            Posting fee: <span className="text-zinc-200 font-medium">{feeLabel}</span>
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-zinc-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!title.trim() || submitting}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
            >
              {submitting && <Loader2 size={14} className="animate-spin" />}
              Create & Pay
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
