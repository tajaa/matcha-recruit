import { Check, X, Clock, ShieldCheck } from 'lucide-react'
import type { CappeBooking } from '../../../types'
import { money } from './constants'

interface PendingRequestsProps {
  pending: CappeBooking[]
  acceptBooking: (b: CappeBooking) => void
  declineBooking: (b: CappeBooking) => void
}

export function PendingRequests({ pending, acceptBooking, declineBooking }: PendingRequestsProps) {
  return (
    <section className="mb-6 rounded-2xl border border-amber-500/30 bg-amber-500/[0.05] p-5">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-amber-200">
        <Clock className="h-4 w-4" /> {pending.length} request{pending.length === 1 ? '' : 's'} awaiting your approval
      </h2>
      <ul className="space-y-2">
        {pending.map((b) => (
          <li key={b.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900 p-3 text-sm">
            <div className="min-w-0 flex-1">
              <div className="truncate text-zinc-100">{b.customer_name || b.customer_email || 'Customer'}</div>
              <div className="text-xs text-zinc-400">
                {new Date(b.starts_at).toLocaleString()} – {new Date(b.ends_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                {' · '}<span className="text-emerald-400">{money(b.quoted_price_cents)}</span>
                {b.rider_acknowledged && <span className="ml-2 inline-flex items-center gap-1 text-zinc-500"><ShieldCheck className="h-3 w-3" /> agreed to rider</span>}
              </div>
              {b.note && <div className="mt-1 truncate text-xs text-zinc-500">“{b.note}”</div>}
            </div>
            <button onClick={() => acceptBooking(b)} className="flex items-center gap-1 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-emerald-400"><Check className="h-3.5 w-3.5" /> Accept</button>
            <button onClick={() => declineBooking(b)} className="flex items-center gap-1 rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800"><X className="h-3.5 w-3.5" /> Decline</button>
          </li>
        ))}
      </ul>
    </section>
  )
}
