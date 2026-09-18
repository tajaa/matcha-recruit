import { Printer } from 'lucide-react'
import { TicketPanel } from './Ticket'

interface TicketState {
  rating: number
  quote: string
  meta: string
}

export function VoidTicket({ before, after }: { before: TicketState; after: TicketState }) {
  return (
    <TicketPanel className="bg-tu-paper p-6 text-tu-ink shadow-[0_20px_45px_rgba(76,55,29,0.12)] sm:rounded-2xl sm:p-8">
      <div className="flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-wider text-tu-ink/55"><Printer className="h-4 w-4" /> Review forgiveness</div>
      <h3 className="mt-3 font-display text-2xl font-semibold sm:text-3xl">A 48-hour reprint window.</h3>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed text-tu-ink/70">Flag a review, and it holds for 48 hours before it publishes — long enough to make a bad visit right. Ratings roll as a running average, not a single ticket stapled to your door forever.</p>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <div className="border-t-2 border-dashed border-tu-ink/25 pt-4">
          <span className="tu-stamp border-tu-bad text-tu-bad">Void</span>
          <div className="mt-4 flex items-center gap-2 font-mono text-sm"><span className="text-tu-bad">{before.rating}★</span><span className="text-tu-ink/45">{before.meta}</span></div>
          <p className="mt-2 text-sm italic text-tu-ink/65">&quot;{before.quote}&quot;</p>
        </div>
        <div className="border-t-2 border-dashed border-tu-ink/25 pt-4">
          <span className="tu-stamp border-tu-good text-tu-good">Resolved</span>
          <div className="mt-4 flex items-center gap-2 font-mono text-sm"><span className="text-tu-good">{after.rating}★</span><span className="text-tu-ink/45">{after.meta}</span></div>
          <p className="mt-2 text-sm italic text-tu-ink/65">&quot;{after.quote}&quot;</p>
        </div>
      </div>
      <p className="mt-5 font-mono text-[10px] uppercase tracking-wide text-tu-ink/45">Illustrative example. The 48-hour hold is real.</p>
    </TicketPanel>
  )
}
