import { Link } from 'react-router-dom'
import { FileText } from 'lucide-react'

interface Props {
  brand: string
  onClose: () => void
}

export function NoResumeModal({ brand, onClose }: Props) {
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div className="relative w-full max-w-sm bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl p-6">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-950 border border-amber-900 flex items-center justify-center shrink-0">
            <FileText size={18} className="text-amber-400" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-zinc-100">Upload your resume to apply</h3>
            <p className="text-xs text-zinc-400 mt-1">
              {brand} uses your parsed profile resume to auto-fill job applications.
              Upload one once and reuse it for every role you apply to.
            </p>
            <div className="mt-4 flex items-center gap-2">
              <Link
                to="/settings"
                onClick={onClose}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg transition-colors"
              >
                Go to Settings
              </Link>
              <button
                onClick={onClose}
                className="px-3 py-1.5 text-xs text-zinc-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
