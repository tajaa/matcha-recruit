import { CheckCircle2, Loader2 } from 'lucide-react'

interface Step4DoneProps {
  onContinue: () => void
  activating?: boolean
  activationTimedOut?: boolean
}

export default function Step4Done({ onContinue, activating, activationTimedOut }: Step4DoneProps) {
  return (
    <div className="text-center py-6 space-y-4">
      <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
      <div>
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">You're set up.</h2>
        <p className="text-sm text-zinc-400">Start filing incidents and tracking your team.</p>
      </div>

      {activating && !activationTimedOut && (
        <div className="flex items-center justify-center gap-2 text-sm text-zinc-400">
          <Loader2 className="w-4 h-4 animate-spin" />
          Activating your account…
        </div>
      )}

      {activationTimedOut && (
        <p className="text-sm text-amber-400">
          Taking longer than expected.{' '}
          <button onClick={onContinue} className="underline">
            Try going to your dashboard
          </button>{' '}
          or refresh the page.
        </p>
      )}

      {!activating && !activationTimedOut && (
        <button
          onClick={onContinue}
          className="bg-emerald-700 hover:bg-emerald-600 text-white font-medium px-6 py-2.5 rounded transition-colors"
        >
          Go to dashboard
        </button>
      )}
    </div>
  )
}
