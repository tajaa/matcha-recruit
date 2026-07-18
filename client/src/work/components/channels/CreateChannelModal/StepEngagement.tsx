import { Clock, AlertTriangle } from 'lucide-react'
import { INACTIVITY_OPTIONS, WARNING_OPTIONS } from './constants'

/* ─── Step 4: Engagement Rules ─── */

export function StepEngagement({
  inactivityDays, setInactivityDays, warningDays, setWarningDays,
}: {
  inactivityDays: number
  setInactivityDays: (v: number) => void
  warningDays: number
  setWarningDays: (v: number) => void
}) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs text-zinc-400 mb-2">
          <Clock size={12} className="inline mr-1 -mt-0.5" />
          Inactivity threshold
        </label>
        <p className="text-[11px] text-zinc-500 mb-2">How long before a member is considered inactive?</p>
        <div className="flex flex-wrap gap-2">
          {INACTIVITY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setInactivityDays(opt.value)}
              className={`px-3 py-1.5 rounded-lg border text-sm transition-colors ${
                inactivityDays === opt.value
                  ? 'border-emerald-600 bg-emerald-600/10 text-emerald-400 font-medium'
                  : 'border-zinc-700 bg-zinc-800 text-zinc-300 hover:border-zinc-600'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-xs text-zinc-400 mb-2">
          <AlertTriangle size={12} className="inline mr-1 -mt-0.5" />
          Warning period
        </label>
        <p className="text-[11px] text-zinc-500 mb-2">How much notice before removal?</p>
        <div className="flex flex-wrap gap-2">
          {WARNING_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setWarningDays(opt.value)}
              className={`px-3 py-1.5 rounded-lg border text-sm transition-colors ${
                warningDays === opt.value
                  ? 'border-emerald-600 bg-emerald-600/10 text-emerald-400 font-medium'
                  : 'border-zinc-700 bg-zinc-800 text-zinc-300 hover:border-zinc-600'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="p-3 bg-zinc-800/50 rounded-lg border border-zinc-700/50">
        <p className="text-xs text-zinc-300 leading-relaxed">
          Members who don't contribute for <span className="text-emerald-400 font-medium">{inactivityDays} days</span> get
          a <span className="text-emerald-400 font-medium">{warningDays}-day warning</span>, then are auto-removed.
          They can rejoin after their billing period ends.
        </p>
      </div>
    </div>
  )
}
