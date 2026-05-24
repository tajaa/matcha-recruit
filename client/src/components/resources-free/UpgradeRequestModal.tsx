import { useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { api } from '../../api/client'

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

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="bg-zinc-900 border border-zinc-800 rounded-lg w-full max-w-sm p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-zinc-100">Request Matcha IR access</h2>
          <button onClick={handleClose} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {done ? (
          <div className="py-2">
            <p className="text-sm text-emerald-400">Request sent — our team will be in touch shortly.</p>
            <button
              onClick={handleClose}
              className="mt-4 w-full border border-zinc-700 text-zinc-300 hover:bg-zinc-800 text-sm py-2 rounded transition-colors"
            >
              Close
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="block text-xs text-zinc-400 uppercase tracking-wide mb-1">
                Number of employees
              </label>
              <input
                type="number"
                min={1}
                value={headcount}
                onChange={(e) => setHeadcount(e.target.value)}
                placeholder="e.g. 25"
                className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-emerald-700"
              />
            </div>
            {error && <p className="text-xs text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm font-medium py-2 rounded transition-colors flex items-center justify-center gap-2"
            >
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              {submitting ? 'Sending…' : 'Request access'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
