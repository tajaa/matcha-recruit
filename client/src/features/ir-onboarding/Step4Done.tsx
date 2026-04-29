import { CheckCircle2 } from 'lucide-react'

export default function Step4Done({ onContinue }: { onContinue: () => void }) {
  return (
    <div className="text-center py-6 space-y-4">
      <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
      <div>
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">You're set up.</h2>
        <p className="text-sm text-zinc-400">Start filing incidents and tracking your team.</p>
      </div>
      <button
        onClick={onContinue}
        className="bg-emerald-700 hover:bg-emerald-600 text-white font-medium px-6 py-2.5 rounded transition-colors"
      >
        Go to dashboard
      </button>
    </div>
  )
}
