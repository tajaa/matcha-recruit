import { AlertTriangle, X } from 'lucide-react'

interface Props {
  daysUntilRemoval: number
  onDismiss: () => void
}

export default function InactivityWarningBanner({ daysUntilRemoval, onDismiss }: Props) {
  return (
    <div className="w-full bg-amber-900/20 border-b border-amber-700/30 px-4 py-2.5 flex items-center gap-3 text-sm text-amber-200">
      <AlertTriangle className="w-4 h-4 shrink-0 text-amber-500" />
      <span className="flex-1">
        You'll be removed from this channel in {daysUntilRemoval} day{daysUntilRemoval !== 1 ? 's' : ''} due to inactivity. Send a message to stay active.
      </span>
      <button
        onClick={onDismiss}
        className="shrink-0 text-amber-400 hover:text-amber-300 transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}
