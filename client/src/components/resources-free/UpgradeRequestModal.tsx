import { useState } from 'react'
import { CheckCircle2, Loader2, Sparkles } from 'lucide-react'
import { api } from '../../api/client'
import { Modal } from '../ui/Modal'

export function UpgradeRequestModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [headcount, setHeadcount] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    const hc = parseInt(headcount, 10)
    try {
      await api.post('/resources/upgrade/lite/request', {
        headcount: isNaN(hc) ? null : hc,
      })
      setDone(true)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setSubmitting(false)
    }
  }

  function handleClose() {
    setDone(false)
    setHeadcount('')
    setError(null)
    onClose()
  }

  return (
    <Modal open={isOpen} onClose={handleClose} title="Request Matcha IR access" width="sm">
      {done ? (
        <div className="flex flex-col items-center gap-3 py-4 text-center">
          <div className="rounded-full bg-emerald-900/30 p-3">
            <CheckCircle2 className="w-6 h-6 text-emerald-400" />
          </div>
          <div>
            <p className="text-sm font-medium text-zinc-100">Request sent</p>
            <p className="text-xs text-zinc-500 mt-1">Our team will reach out to you shortly.</p>
          </div>
          <button
            onClick={handleClose}
            className="mt-2 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            Close
          </button>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <div className="flex items-center gap-2 p-3 rounded-lg bg-emerald-900/15 border border-emerald-800/30">
            <Sparkles className="w-4 h-4 text-emerald-400 shrink-0" />
            <p className="text-xs text-zinc-400 leading-relaxed">
              Unlock incident reporting, employee records, and discipline workflows.
            </p>
          </div>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1.5">
              Number of employees
            </label>
            <input
              type="number"
              min={1}
              max={300}
              value={headcount}
              onChange={(e) => setHeadcount(e.target.value)}
              placeholder="e.g. 25"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700 transition-colors"
            />
          </div>
          {error && (
            <p className="text-xs text-red-400 bg-red-950/30 border border-red-900/30 rounded px-3 py-2">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {submitting ? 'Sending…' : 'Request access'}
          </button>
        </form>
      )}
    </Modal>
  )
}
