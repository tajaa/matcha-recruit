import { Globe, DollarSign, Check, Zap, Users } from 'lucide-react'
import type { AccessModel } from './types'

/* ─── Step 2: Access Model ─── */

export function StepAccessModel({
  accessModel, setAccessModel,
}: {
  accessModel: AccessModel
  setAccessModel: (v: AccessModel) => void
}) {
  const models: {
    value: AccessModel
    icon: typeof Globe
    title: string
    description: string
    badge?: string
  }[] = [
    {
      value: 'free',
      icon: Users,
      title: 'Free',
      description: 'Anyone can join and participate. Great for community channels and open discussions.',
    },
    {
      value: 'paid',
      icon: DollarSign,
      title: 'Paid Subscription',
      description: 'Members pay a monthly fee to access the channel. No activity requirements.',
      badge: 'Recurring',
    },
    {
      value: 'paid_engagement',
      icon: Zap,
      title: 'Paid + Engagement',
      description: 'Monthly fee with activity requirements. Inactive members are auto-removed to keep the community engaged.',
      badge: 'Active',
    },
  ]

  return (
    <div className="space-y-2.5">
      <p className="text-xs text-zinc-400 mb-3">How should members access this channel?</p>
      {models.map((m) => (
        <button
          key={m.value}
          type="button"
          onClick={() => setAccessModel(m.value)}
          className={`w-full text-left p-3.5 rounded-lg border transition-all ${
            accessModel === m.value
              ? 'border-emerald-600 bg-emerald-600/10'
              : 'border-zinc-700 bg-zinc-800/50 hover:border-zinc-600'
          }`}
        >
          <div className="flex items-start gap-3">
            <div className={`mt-0.5 p-1.5 rounded-md ${
              accessModel === m.value ? 'bg-emerald-600/20 text-emerald-400' : 'bg-zinc-700/50 text-zinc-400'
            }`}>
              <m.icon size={16} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className={`text-sm font-medium ${
                  accessModel === m.value ? 'text-emerald-400' : 'text-zinc-200'
                }`}>{m.title}</span>
                {m.badge && (
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                    accessModel === m.value
                      ? 'bg-emerald-600/20 text-emerald-400'
                      : 'bg-zinc-700 text-zinc-400'
                  }`}>{m.badge}</span>
                )}
              </div>
              <p className="text-xs text-zinc-500 mt-0.5 leading-relaxed">{m.description}</p>
            </div>
            <div className={`mt-1 w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
              accessModel === m.value
                ? 'border-emerald-500 bg-emerald-500'
                : 'border-zinc-600'
            }`}>
              {accessModel === m.value && <Check size={10} className="text-white" />}
            </div>
          </div>
        </button>
      ))}
    </div>
  )
}
