import type { LucideIcon } from 'lucide-react'
import { TicketPanel } from './Ticket'

export interface ReceiptRow {
  icon: LucideIcon
  label: string
  body: string
  value: string
}

export function ReceiptList({
  eyebrow,
  rows,
  total,
}: {
  eyebrow: string
  rows: ReceiptRow[]
  total: { label: string; value: string }
}) {
  return (
    <TicketPanel className="bg-tu-paper p-6 pb-7 text-tu-ink shadow-[0_20px_45px_rgba(76,55,29,0.12)] sm:rounded-2xl sm:p-8">
      <div className="mb-5 flex items-center justify-between border-b-2 border-tu-ink pb-3 font-mono text-xs font-bold uppercase tracking-wider">
        <span>{eyebrow}</span>
        <span className="text-tu-ink/45">Tell-Us</span>
      </div>
      <div className="divide-y divide-dashed divide-tu-ink/15">
        {rows.map(({ icon: Icon, label, body, value }) => (
          <div key={label} className="grid gap-2 py-5 sm:grid-cols-[auto_1fr] sm:gap-4">
            <span className="flex h-10 w-10 items-center justify-center rounded-sm bg-tu-ink/10 text-tu-ink">
              <Icon className="h-5 w-5" />
            </span>
            <div>
              <div className="flex items-baseline gap-2 font-mono text-xs font-bold uppercase tracking-wide">
                <span>{label}</span>
                <span className="tu-leader" />
                <span className="shrink-0 text-tu-ink/60">{value}</span>
              </div>
              <p className="mt-1.5 text-sm leading-relaxed text-tu-ink/70">{body}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-1 flex items-baseline gap-2 border-t-2 border-tu-ink pt-4 font-mono text-xs font-bold uppercase tracking-wide">
        <span>{total.label}</span>
        <span className="tu-leader" />
        <span className="shrink-0 text-tu-accent">{total.value}</span>
      </div>
    </TicketPanel>
  )
}
