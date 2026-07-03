import { Loader2, X } from 'lucide-react'
import { Stat } from './Sparkline'
import type { Analytics } from './types'

export function AnalyticsDrawer({
  setAnalyticsOpen, analytics,
}: {
  setAnalyticsOpen: (v: string | null) => void
  analytics: Analytics | null
}) {
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => setAnalyticsOpen(null)}>
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-zinc-100">Issue analytics</h3>
          <button onClick={() => setAnalyticsOpen(null)} className="text-zinc-500 hover:text-zinc-300"><X size={16} /></button>
        </div>
        {!analytics ? (
          <Loader2 className="animate-spin text-zinc-500" size={16} />
        ) : (
          <div className="grid grid-cols-2 gap-3 text-xs">
            <Stat label="Sent" value={analytics.sent} />
            <Stat label="Failed" value={analytics.failed} />
            <Stat label="Open rate" value={`${(analytics.open_rate * 100).toFixed(1)}%`} sub={`${analytics.opened} opens`} />
            <Stat label="Click rate" value={`${(analytics.click_rate * 100).toFixed(1)}%`} sub={`${analytics.clicked} unique`} />
            <Stat label="Bounce rate" value={`${(analytics.bounce_rate * 100).toFixed(1)}%`} sub={`${analytics.bounced} bounced`} />
            <Stat label="Unsubscribes" value={analytics.unsubscribed_window} sub="7-day window" />
          </div>
        )}
      </div>
    </div>
  )
}
