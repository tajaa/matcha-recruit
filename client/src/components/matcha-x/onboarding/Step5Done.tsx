import { ArrowRight, ShieldCheck } from 'lucide-react'

export default function Step5Done({ onFinish }: { onFinish: () => void }) {
  return (
    <div className="text-center py-12 space-y-6">
      <div className="mx-auto w-14 h-14 rounded-2xl bg-emerald-900/40 ring-1 ring-emerald-800 flex items-center justify-center">
        <ShieldCheck className="w-7 h-7 text-emerald-400" />
      </div>
      <div>
        <h2 className="text-xl font-semibold text-zinc-100">You're all set</h2>
        <p className="text-sm text-zinc-400 mt-2 max-w-md mx-auto">
          Your compliance baseline is live and tracked. We'll keep watching the law for
          every jurisdiction you operate in and flag changes as they happen.
        </p>
      </div>
      <button
        onClick={onFinish}
        className="inline-flex items-center gap-2 bg-emerald-700 hover:bg-emerald-600 text-white font-medium px-6 py-2.5 rounded-lg transition-colors"
      >
        Go to your dashboard <ArrowRight className="w-4 h-4" />
      </button>
    </div>
  )
}
