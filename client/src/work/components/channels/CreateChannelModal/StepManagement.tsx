import { DollarSign, Shield, Zap, Users, Clock, AlertTriangle } from 'lucide-react'
import type { AccessModel } from './types'

/* ─── Step 6: Management Guide ─── */

export function StepManagement({ accessModel, inactivityDays }: { accessModel: AccessModel; inactivityDays: number }) {
  const guides = [
    {
      icon: <Users size={16} className="text-emerald-400" />,
      title: 'Member Management',
      desc: 'View all subscribers in the channel member list. Promote trusted members to moderators who can help manage content.',
    },
    {
      icon: <DollarSign size={16} className="text-emerald-400" />,
      title: 'Revenue Dashboard',
      desc: 'Click the Settings gear icon in your channel header to see subscriber count, monthly recurring revenue, and total earnings.',
    },
    {
      icon: <Shield size={16} className="text-emerald-400" />,
      title: 'Invite Links',
      desc: 'Generate shareable invite links from the channel header. Each link can be set to expire or be single-use for controlled access.',
    },
    ...(accessModel === 'paid_engagement' ? [{
      icon: <Clock size={16} className="text-amber-400" />,
      title: 'Inactivity Auto-Removal',
      desc: `Members who don't contribute for ${inactivityDays} days receive a warning banner. After the warning period, they're auto-removed. They can rejoin once their current billing period ends.`,
    }] : []),
    {
      icon: <AlertTriangle size={16} className="text-amber-400" />,
      title: 'Failed Payments',
      desc: 'If a subscriber\'s payment fails, their status changes to "past due." They keep access until the end of their billing period, then lose it automatically.',
    },
    {
      icon: <Zap size={16} className="text-emerald-400" />,
      title: 'Tips & Gifts',
      desc: 'Subscribers can send you one-time tips from within the channel. Tip amounts appear in your revenue dashboard for visibility — funds are held by the platform until creator payouts ship.',
    },
  ]

  return (
    <div className="space-y-3">
      <p className="text-xs text-zinc-400 mb-1">Here's how to manage your paid channel after creation.</p>
      <div className="space-y-2 max-h-[280px] overflow-y-auto pr-1">
        {guides.map((g) => (
          <div key={g.title} className="flex gap-3 p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/40">
            <div className="mt-0.5 shrink-0">{g.icon}</div>
            <div>
              <p className="text-xs font-medium text-zinc-200">{g.title}</p>
              <p className="text-[11px] text-zinc-500 leading-relaxed mt-0.5">{g.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
