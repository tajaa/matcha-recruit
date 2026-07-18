import { useState } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { createAnalysisSession, type AnalysisSession } from '../../../api/analysis-pilot/analysisPilot'

// --------------------------------------------------------------------------- //
// NewSessionModal
// --------------------------------------------------------------------------- //

export function NewSessionModal({ onClose, onCreated }: { onClose: () => void; onCreated: (s: AnalysisSession) => void }) {
  const [title, setTitle] = useState('')
  const [domain, setDomain] = useState('')
  const [goal, setGoal] = useState('')
  const [busy, setBusy] = useState(false)

  const create = async () => {
    if (!title.trim() || busy) return
    setBusy(true)
    try {
      const s = await createAnalysisSession({ title: title.trim(), domain: domain || undefined, goal: goal.trim() || undefined })
      onCreated(s)
    } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-950 p-5" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-semibold text-zinc-100 mb-4 flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-emerald-500" /> New analysis
        </h3>
        <label className="block text-xs text-zinc-400 mb-1">Title</label>
        <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="Q3 portfolio volatility"
          className="w-full rounded-lg bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-zinc-200 mb-3 focus:outline-none focus:border-emerald-500" />
        <label className="block text-xs text-zinc-400 mb-1">Domain <span className="text-zinc-600">(optional)</span></label>
        <select value={domain} onChange={(e) => setDomain(e.target.value)}
          className="w-full rounded-lg bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-zinc-200 mb-3">
          <option value="">General</option>
          <option value="financial">Financial</option>
          <option value="insurance">Insurance / P&C</option>
          <option value="sports">Sports</option>
          <option value="operations">Operations / Inventory</option>
        </select>
        <label className="block text-xs text-zinc-400 mb-1">What do you want to understand? <span className="text-zinc-600">(optional)</span></label>
        <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3}
          placeholder="e.g. What's the revenue trend? How volatile are these returns?"
          className="w-full rounded-lg bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-zinc-200 mb-4 focus:outline-none focus:border-emerald-500" />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-2 text-sm text-zinc-400 hover:text-zinc-200">Cancel</button>
          <button onClick={() => void create()} disabled={!title.trim() || busy}
            className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-medium inline-flex items-center gap-2">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Create
          </button>
        </div>
      </div>
    </div>
  )
}
