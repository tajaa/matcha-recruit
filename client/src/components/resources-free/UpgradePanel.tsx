import { useState } from 'react'
import { AlertTriangle, MessageSquare, Sparkles } from 'lucide-react'

import { PricingContactModal } from '../PricingContactModal'
import { UpgradeRequestModal } from './UpgradeRequestModal'

export default function UpgradePanel() {
  const [contactOpen, setContactOpen] = useState(false)
  const [requestOpen, setRequestOpen] = useState(false)

  return (
    <>
      <div className="rounded-md p-3 bg-gradient-to-br from-emerald-900/40 to-zinc-900/60 border border-emerald-800/40">
        <div className="flex items-center gap-1.5 mb-2">
          <Sparkles className="h-3.5 w-3.5 text-emerald-300" strokeWidth={2} />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
            Upgrade
          </span>
        </div>
        <p className="text-[11.5px] text-zinc-300 leading-snug mb-3">
          Add Matcha IR for incident reporting + employee management.
        </p>
        <button
          type="button"
          onClick={() => setRequestOpen(true)}
          className="flex items-center justify-center gap-1.5 w-full rounded-md px-2.5 py-1.5 text-[12px] font-medium bg-emerald-600 hover:bg-emerald-500 text-white transition-colors"
        >
          <AlertTriangle className="h-3.5 w-3.5" strokeWidth={2} />
          Upgrade to Matcha IR
        </button>
        <button
          type="button"
          onClick={() => setContactOpen(true)}
          className="flex items-center justify-center gap-1.5 w-full mt-2 rounded-md px-2.5 py-1.5 text-[12px] font-medium border border-zinc-700 text-zinc-300 hover:bg-zinc-800/50 transition-colors"
        >
          <MessageSquare className="h-3.5 w-3.5" strokeWidth={1.6} />
          Get full platform
        </button>
      </div>

      <UpgradeRequestModal isOpen={requestOpen} onClose={() => setRequestOpen(false)} />
      <PricingContactModal isOpen={contactOpen} onClose={() => setContactOpen(false)} />
    </>
  )
}
